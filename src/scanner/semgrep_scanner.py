from __future__ import annotations
import re
import os
import ast
import json
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any, Optional

@dataclass
class Issue:
    type: str
    file: str
    line: int
    message: str
    snippet: str

    def __hash__(self):
        return hash((self.type, self.file, self.line, self.message))

    def __eq__(self, other):
        return (
            isinstance(other, Issue)
            and self.type == other.type
            and self.file == other.file
            and self.line == other.line
            and self.message == other.message
        )


class StaticScanner:
    def __init__(self, project_root: Path, logger=None):
        self.project_root = Path(project_root).resolve()
        self.logger = logger

    def scan(self, files: Optional[List[str]] = None) -> List[Issue]:
        issues: List[Issue] = []

        # 1. 使用 Semgrep 扫描（核心：识别真实 bug）
        issues += self._scan_with_semgrep(files)

        # 2. （可选）保留原有的未使用变量检测（可关闭）
        if os.getenv("ENABLE_UNUSED_VAR_CHECK", "0") == "1":
            issues += self._scan_with_ast(files)

        # 3. 去重（Semgrep 和 AST 可能重复）
        unique_issues = list(set(issues))
        return sorted(unique_issues, key=lambda x: (x.file, x.line))

    # ==============================
    # 🔍 Semgrep 扫描（主力）
    # ==============================
    def _scan_with_semgrep(self, files: Optional[List[str]] = None) -> List[Issue]:
        """调用 Semgrep 扫描项目，返回标准化 Issue 列表"""
        if not self._is_semgrep_available():
            if self.logger:
                self.logger.warning("Semgrep not found. Skipping advanced bug detection.")
            return []

        cmd = ["semgrep", "scan", "--json"]

        # 添加常用规则集（安全 + bug + 最佳实践）
        cmd += [
            "--config", "p/python",
            "--config", "p/javascript",
            "--config", "p/typescript",
            "--config", "p/security-audit",
            "--config", "p/bug-detectors"
        ]

        # 如果指定了文件，只扫描这些文件
        if files:
            cmd += ["--include"] + [str(f) for f in files]

        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=300,  # 5分钟超时
                env={**os.environ, "PYTHONIOENCODING": "utf-8"}
            )

            if result.returncode not in (0, 1):
                if self.logger:
                    self.logger.error(f"Semgrep failed: {result.stderr}")
                return []

            output = json.loads(result.stdout)
            issues = []
            for finding in output.get("results", []):
                # 提取关键信息
                check_id = finding["check_id"]
                path = finding["path"]
                start_line = finding["start"]["line"]
                message = finding["extra"]["message"]
                lines = finding["extra"].get("lines", "").strip()

                # 标准化文件路径（相对 project_root）
                try:
                    rel_path = str(Path(path).relative_to(self.project_root))
                except ValueError:
                    rel_path = path  # 不在项目内？保留原路径

                issues.append(Issue(
                    type=check_id.split(".")[-1],
                    file=rel_path,
                    line=start_line,
                    message=message,
                    snippet=lines
                ))
            return issues

        except subprocess.TimeoutExpired:
            if self.logger:
                self.logger.error("Semgrep scan timed out")
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error running Semgrep: {e}")
        return []

    def _scan_python(self, rel: str, text: str) -> List[Issue]:
        issues: List[Issue] = []
        try:
            tree = ast.parse(text)
        except SyntaxError as e:
            issues.append(Issue("SyntaxError", rel, e.lineno or 1, str(e), self._line(text, e.lineno)))
            return issues

        assigned = set()
        used = set()

        class UseVisitor(ast.NodeVisitor):
            def visit_Name(self, node):
                if isinstance(node.ctx, ast.Store):
                    assigned.add(node.id)
                elif isinstance(node.ctx, ast.Load):
                    used.add(node.id)

        UseVisitor().visit(tree)

        for name in sorted(assigned - used):
            if name.startswith("_") or name in ("self", "cls"):
                continue
            if re.search(rf"\b{name}\b.*(log|logger|print|debug)", text, re.IGNORECASE):
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if re.search(rf"\b{name}\s*=", line):
                    issues.append(Issue(
                        "UnusedVariable",
                        rel,
                        i,
                        f"Variable '{name}' assigned but never used",
                        line.strip()
                    ))
                    break
        return issues

    # ==============================
    # 🛠 工具方法
    # ==============================
    def _is_semgrep_available(self) -> bool:
        """检查 semgrep 是否已安装"""
        try:
            subprocess.run(["semgrep", "--version"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def _line(self, text: str, n: int) -> str:
        if not n:
            return ""
        lines = text.splitlines()
        n = max(1, min(n, len(lines)))
        return lines[n - 1].strip()