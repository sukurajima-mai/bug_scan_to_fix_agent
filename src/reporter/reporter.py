from __future__ import annotations
import json, os
from datetime import datetime
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any, Tuple
from ..analyzer.multiLangIssueAnalyzer import Issue

class Reporter:
    def __init__(self, project_root: str, logger):
        self.project_root = Path(project_root)
        self.logger = logger
        self.items: List[Dict[str, Any]] = []

    def add_item(self, issue: Issue, status: str, detail: dict, suggested_fix: str = "", original_snippet: str = ""):
        """
        添加报告项，包含修复建议和原始代码片段。
        """
        payload = {
            "slug": issue.slug,
            "language": issue.language,
            "bug_type": issue.bug_type,
            "bug_message": issue.bug_message,
            "description": issue.description,
            "constraints": issue.constraints,
            "buggy_code": issue.buggy_code,
            "fixed_code": issue.fixed_code, # 记录修复后的代码
            "status": status,
            "detail": detail,
        }
        self.items.append(payload)

    def _generate_markdown_report(self, summary: Dict[str, Any]) -> str:
        """生成规范的 Markdown 报告内容"""
        md_lines = []
        md_lines.append(f"# Bug 自动修复 Agent 报告")
        md_lines.append(f"\n## 摘要")
        md_lines.append(f"- **总共发现问题:** {summary['total_issues']}")
        md_lines.append(f"- **成功修复:** {summary['total_fixed']}")
        md_lines.append(f"- **验证失败/未修复:** {summary['total_failed']}")
        md_lines.append(f"- **报告生成时间:** {summary['timestamp']}")
        md_lines.append("\n## 问题详情")

        for i, item in enumerate(self.items, 1):
            status = item['status']
            # 根据状态确定文本描述
            status_text = "✅ 修复并验证通过" if status == 'fixed' else "❌ 验证失败并回滚" if status == 'failed' and item['detail'].get('reason') == 'validation failed, rolled back' else "⚠️ 修复失败/未实现"
            
            # 规范代码块语言名称
            lang_code = item.get('language', 'Unknown').lower().replace('python3', 'python').replace('cpp', 'c++').replace('java', 'java')
            
            md_lines.append(f"\n### {i}. [{status_text}] {item['slug']} ({item['language']})")
            # md_lines.append(f"- **Bug 类型:** {item['bug_type']}")
            md_lines.append(f"- **Bug 描述:** {item['bug_message']}")
            md_lines.append(f"- **题目描述:** {item['description'][:100]}...") # 截断描述
            
            md_lines.append("\n#### 原始 Buggy 代码:")
            md_lines.append(f"```{lang_code}\n{item['buggy_code'].strip()}\n```")
            
            if item['status'] == 'fixed':
                 md_lines.append("\n#### 修复后代码 (已验证):")
                 md_lines.append(f"```{lang_code}\n{item['fixed_code'].strip()}\n```")
            elif item['fixed_code'] and status == 'failed':
                 md_lines.append("\n#### 修复尝试代码 (验证失败，未提交):")
                 md_lines.append(f"```{lang_code}\n{item['fixed_code'].strip()}\n```")
            
            # 结果状态
            md_lines.append(f"\n- **最终状态:** **{status_text}**")
            if status == 'failed':
                 md_lines.append(f"- **失败原因:** {item['detail'].get('reason', '未知')}")
                 md_lines.append(f"- **注意:** 由于验证失败，文件已回滚到原始状态。")

        return "\n".join(md_lines)

    def write(self, fixed: int, failed: int, output_dir: Path = None) -> Tuple[str, str]:
        """写入 JSON 和 Markdown 报告"""
        
        # 如果传入了特定目录就用它，否则用默认根目录
        target_path = output_dir if output_dir else self.project_root
        
        # 确保目录存在
        if not target_path.exists():
            target_path.mkdir(parents=True, exist_ok=True)

        summary = {
            "total_issues": len(self.items),
            "total_fixed": fixed,
            "total_failed": failed,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        data = {"summary": summary, "items": self.items}
        
        # 1. JSON Report
        json_path = target_path / "bug_fix_report.json" # 使用 Path 的 / 操作符
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            json_report_output = f"JSON 报告已保存至: {json_path}"
        except Exception as e:
            json_report_output = f"❌ JSON 报告保存失败: {e}"

        # 2. Markdown Report
        md_content = self._generate_markdown_report(summary)
        md_path = target_path / "bug_fix_report.md"
        try:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md_content)
            md_report_output = f"Markdown 报告已保存至: {md_path}"
        except Exception as e:
            md_report_output = f"❌ Markdown 报告保存失败: {e}"
            
        txt_lines = [
            "智能纠错统计", 
            f"成功修复: {fixed}", 
            f"失败: {failed}",
            json_report_output,
            md_report_output
        ]
        
        return "\n".join(txt_lines), json.dumps(data, ensure_ascii=False, indent=2)