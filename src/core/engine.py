import logging, json, os, sys, re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# --- MODIFICATION 1: 更新导入（使用新的分析器和 Issue 数据结构）---
# 假设 engine.py 在 src/core/ 中，使用相对导入
from ..analyzer.multiLangIssueAnalyzer import MultiLangIssueAnalyzer, Issue 

from src.fixer.auto_fixer import AutoFixer
from src.validator.validator import Validator
from src.reporter.reporter import Reporter

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"

class BugFixEngine:
    def __init__(self, project_root: str, max_iterations: int = 4, logger=None):
        self.project_root = Path(project_root).resolve()
        self.max_iterations = max_iterations
        self.logger = logger or self._make_logger()
        # 替换扫描器初始化
        self.scanner = MultiLangIssueAnalyzer(self.logger)
        # 修复器现在专注于代码片段
        self.fixer = AutoFixer(self.project_root, self.logger) 
        # 验证器现在将验证代码片段
        self.validator = Validator(self.project_root, self.logger)
        # 报告器也适应新的 Issue 结构
        self.reporter = Reporter(self.project_root, self.logger)

    def _make_logger(self):
        logger = logging.getLogger("BugFixEngine")
        if not logger.handlers:
            logger.setLevel(logging.INFO)
            ch = logging.StreamHandler()
            ch.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
            logger.addHandler(ch)
        return logger

    def _print_header(self, title):
        print(f"{CYAN}{'='*60}{RESET}")
        print(f"{CYAN}{title}{RESET}")
        print(f"{CYAN}{'='*60}{RESET}")

    def _indent_block(self, s: str) -> str:
        return "\n".join("  "+line for line in s.splitlines())

    # --- MODIFICATION 2: 移除文件 I/O 辅助方法 ---
    # _read_file_line 和 _print_diff 不再需要

    # --- MODIFICATION 3: run 方法更新为代码片段流程 ---
    def run(self, json_reports: List[Dict | str]):
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            self.logger.error("❌ 未配置 API Key，无法进行修复！")
            return
        self.fixer = AutoFixer(self.project_root, self.logger, api_key=api_key)
        self._print_header("Bug自动修复Agent v3.0（代码片段验证增强版）")
        print(f"报告输出路径: {self.project_root}")
        print(f"最大迭代次数: {self.max_iterations}")
        print("-" * 60)

        issues_dicts = self.scanner.analyze_reports(json_reports=json_reports)
        # 从字典转换回 Issue 对象（Issue 结构已更新）
        issues = [Issue(**d) for d in issues_dicts]

        print(f"{YELLOW}初步检测：发现潜在Bug {len(issues)} 个{RESET}")
        fixed = 0
        failed = 0

        for idx, issue in enumerate(issues, 1):
            print(f"\n[#{idx:02d}] 题目场景：{issue.slug}")
            # print(f"Bug类型: {issue.bug_type}")
            # print(f"语言: {issue.language}")
            print(f"Bug信息: {issue.bug_message}")
            # 使用新的 buggy_code 字段
            print(f"Buggy 代码片段:\n{self._indent_block(issue.buggy_code)[:200]}...")

            # # 场景3：修复方案动态优化（LLM 建议文档）
            # print("\n场景3：修复方案动态优化（LLM 建议文档）")
            # # 这里的 LLM 建议（plan_v1/v2）现在只是文档，不是实际要应用的代码
            # plan_v1 = self._suggest_fix_v1(issue)
            # plan_v2 = self._suggest_fix_v2(issue)
            # final_plan_doc = (plan_v2 if plan_v2 and plan_v2 != plan_v1 else plan_v1)
            
            # print(f"最终建议文档:\n{self._indent_block(final_plan_doc)}")
            final_plan_doc = ""
            # 场景3.1：修复代码生成（AutoFixer 负责生成 issue.fixed_code）
            print("\n场景3.1：修复代码生成")
            # apply_fix 现在在内存中操作，并填充 issue.fixed_code 字段
            fix_attempted = self.fixer.apply_fix(issue)
            
            if fix_attempted:
                print(f"{GREEN}✓ 修复代码已生成，长度 {len(issue.fixed_code)}。准备验证。{RESET}")
                # 场景4：测试驱动的验证
                print("\n场景4：测试驱动的验证")
                
                # validator 应该使用 issue.fixed_code 来运行测试
                validation_passed = self.validator.run_tests(issue) 
                
                if validation_passed:
                    # 验证通过
                    print(f"{GREEN}✓ 验证通过：修复代码有效。{RESET}")
                    # Reporter 记录：已修复
                    self.reporter.add_item(
                        issue, 
                        "fixed", 
                        {"plan_doc": final_plan_doc}, 
                        suggested_fix=final_plan_doc # 使用 LLM 建议文档
                    )
                    fixed += 1
                else:
                    # 验证失败 - 只需要报告失败，无需回滚文件
                    print(f"{RED}✗ 验证失败：修复代码无效。{RESET}")
                    # Reporter 记录：失败
                    self.reporter.add_item(
                        issue, 
                        "failed", 
                        {"reason": "validation failed", "plan_doc": final_plan_doc}, 
                        suggested_fix=final_plan_doc
                    )
                    failed += 1
            else:
                # 修复器未能生成代码 (apply_fix 返回 False)
                print(f"{RED}✗ 自动修复失败：未生成有效修复代码。{RESET}")
                self.reporter.add_item(
                    issue, 
                    "failed", 
                    {"reason": "auto-fixer failed to generate code"}, 
                    suggested_fix=final_plan_doc
                )
                failed += 1

        # --- 修改开始：生成时间戳目录 ---
        
        # 1. 生成时间戳字符串 (例如: 20231119_143005)
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 2. 创建 reports 文件夹下的子文件夹
        # 最终路径类似: D:\...\reports\report_20231119_143005
        report_output_dir = self.project_root / "reports" / f"report_{timestamp_str}"
        
        print(f"\n📂 创建本次运行报告目录: {report_output_dir}")
        
        # 3. 调用 reporter.write 时传入这个新目录
        report_txt, report_json = self.reporter.write(
            fixed=fixed, 
            failed=failed, 
            output_dir=report_output_dir
        )
        
        # --- 修改结束 ---

        print("\n报告摘要：")
        print(report_txt)
        return fixed, failed, report_txt, report_json

    # --- MODIFICATION 4: 修复方案文档生成器（简化版） ---
    def _suggest_fix_v1(self, issue: Issue) -> str:
        # 使用新的 bug_type 和 language 字段
        bug_type = issue.bug_type.lower()
        lang = issue.language.lower()
        
        if "misusedoperator" in bug_type and "python" in lang:
            return "# 修复方案 v1: 将赋值运算符 '=' 更改为比较运算符 '=='。"
        elif "redundantcondition" in bug_type and "java" in lang:
            return "// 修复方案 v1: 简化冗余的逻辑条件，例如 (A || (A && B)) 简化为 A。"
        elif "bufferoverflow" in bug_type and "cpp" in lang:
            return "// 修复方案 v1: 检查所有数组索引和边界条件，确保不会越界访问内存。"
        return "// 该问题需人工审查（自动修复文档未实现）"

    def _suggest_fix_v2(self, issue: Issue) -> str:
        # 优化方案（LLM 可能会提供更详细的代码）
        bug_type = issue.bug_type.lower()
        lang = issue.language.lower()

        if "misusedoperator" in bug_type and "python" in lang:
            return """# 修复方案 v2（优化）
# 推荐使用 AST (抽象语法树) 确保只替换 if、while、for 等控制结构中的赋值操作。
# 例如：'if (a = b):' -> 'if (a == b):'"""
        return ""