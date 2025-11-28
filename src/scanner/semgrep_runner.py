import subprocess
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any

class SemgrepRunner:
    def __init__(self, logger=None):
        self.logger = logger

    
    def _find_semgrep_executable(self) -> str:
        """
        针对 Windows 虚拟环境 (.venv) 的终极定位方案
        """
        # 1. 获取当前运行 Python 的根目录 (如果激活了 venv，这就是 .venv 的路径)
        base_prefix = Path(sys.prefix)
        
        # 2. 也是很常见的：用户可能没激活 venv，但 .venv 就在当前目录下
        current_dir_venv = Path(os.getcwd()) / ".venv"

        # 列出所有可能的藏身之处
        candidates = [
            # 优先 1: 当前环境的 Scripts (Windows 标准虚拟环境)
            base_prefix / "Scripts" / "semgrep.exe",
            
            # 优先 2: 当前目录下的 .venv/Scripts (未激活环境时用)
            current_dir_venv / "Scripts" / "semgrep.exe",
            
            # 优先 3: Linux/Mac 的 bin 目录 (以防万一)
            base_prefix / "bin" / "semgrep",
            current_dir_venv / "bin" / "semgrep",
        ]

        print(f"🕵️ 正在寻找 Semgrep...")
        for path in candidates:
            # 打印出来调试一下，看看它找了哪里
            # print(f"  - 检查路径: {path}") 
            if path.exists():
                print(f"✅ 成功定位: {path}")
                return str(path)
        
        # 如果还是找不到，说明可能没装好，或者名字不对
        print("⚠️ 未能在标准路径找到 semgrep.exe，尝试全局命令...")
        return "semgrep"

    def scan_directory(self, target_dir: str, config: str = "auto") -> List[Dict[str, Any]]:
        """
        运行 Semgrep 扫描指定目录，并返回标准化的报告列表
        :param target_dir: 要扫描的本地目录路径
        :param config: Semgrep 配置 (auto, p/default, p/ci 等)
        :return: 符合 MultiLangIssueAnalyzer 输入格式的字典列表
        """
        target_path = Path(target_dir).resolve()
        
        if not target_path.exists():
            if self.logger:
                self.logger.error(f"❌ 目标目录不存在: {target_path}")
            return []

        print(f"🔍 正在使用 Semgrep 扫描目录: {target_path} (Config: {config})...")
        
        # 1. 构造 Semgrep 命令
        # --json: 输出 JSON 格式
        # --quiet: 不输出进度条
        # --no-git-ignore: 扫描所有文件 (可选)
        cmd = [
            "semgrep", 
            "--config", config, 
            "--json", 
            str(target_path)
        ]

        try:
            # 2. 调用子进程执行
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
            
            if result.returncode != 0 and not result.stdout:
                # Semgrep returncode 0=无bug, 1=有bug, 但如果有 stderr 且无 stdout 则是报错
                if self.logger:
                    self.logger.error(f"Semgrep 运行失败: {result.stderr}")
                return []

            # 3. 解析 Semgrep 的原始 JSON
            raw_data = json.loads(result.stdout)
            semgrep_results = raw_data.get("results", [])
            
            print(f"📄 Semgrep 发现了 {len(semgrep_results)} 个潜在问题。")
            
            # 4. 转换为 Engine 标准格式
            return self._transform_to_engine_format(semgrep_results, target_path)

        except FileNotFoundError:
            if self.logger:
                self.logger.error("❌ 未找到 'semgrep' 命令。请先运行 `pip install semgrep`。")
            return []
        except json.JSONDecodeError:
            if self.logger:
                self.logger.error("❌ Semgrep 输出的 JSON 格式无效。")
            return []
        except Exception as e:
            if self.logger:
                self.logger.error(f"扫描过程发生未知错误: {e}")
            return []

    def _transform_to_engine_format(self, results: List[Dict], root_dir: Path) -> List[Dict[str, Any]]:
        """
        将 Semgrep 的 result 结构转换为 Engine 的 Issue 结构
        """
        standard_reports = []

        for item in results:
            try:
                # 提取关键字段
                check_id = item.get("check_id", "semgrep-rule")
                path_str = item.get("path", "")
                full_file_path = root_dir / path_str
                
                start_line = item["start"]["line"]
                end_line = item["end"]["line"]
                
                message = item["extra"]["message"]
                severity = item["extra"].get("severity", "WARNING")
                
                # 提取有问题的代码片段 (Buggy Code)
                # Semgrep JSON sometimes gives 'lines', but reading file is safer for context
                code_snippet = self._read_file_segment(full_file_path, start_line, end_line)
                
                # 构造符合 multiLangIssueAnalyzer 的字典
                issue_dict = {
                    "slug": f"{Path(path_str).name}:{start_line}", # 用文件名+行号作为唯一标识
                    "description": f"Semgrep Audit: {message}",     # 描述
                    "constraints": f"Security/Best-practice rule: {check_id}", # 约束条件
                    "buggy_code": code_snippet,
                    "language": self._infer_lang_from_ext(path_str), # 简单的后缀判断
                    "bug_type": f"{severity} - {check_id}",
                    "bug_message": message,
                    # Semgrep 有时会提供 autofix，也可以利用
                    # "suggested_fix": item["extra"].get("fix", "") 
                }
                standard_reports.append(issue_dict)
                
            except Exception as e:
                # 容错处理，防止单个解析失败影响整体
                print(f"⚠️ 解析 Semgrep 条目失败: {e}")
                continue

        return standard_reports

    def _read_file_segment(self, file_path: Path, start: int, end: int, context: int = 2) -> str:
        """读取文件的指定行范围，并增加一点上下文"""
        if not file_path.exists():
            return ""
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                
            # 调整行号 (list index 从 0 开始)
            # 增加 context 上下文行，但不越界
            idx_start = max(0, start - 1 - context)
            idx_end = min(len(lines), end + context)
            
            return "".join(lines[idx_start:idx_end])
        except Exception:
            return ""

    def _infer_lang_from_ext(self, filename: str) -> str:
        ext = Path(filename).suffix.lower()
        if ext in ['.py']: return 'python'
        if ext in ['.java']: return 'java'
        if ext in ['.cpp', '.c', '.h', '.hpp']: return 'cpp'
        if ext in ['.js', '.ts']: return 'javascript'
        return 'Unknown'