from __future__ import annotations
import json
import requests
import re
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

# 保留核心数据结构
@dataclass
class Issue:
    """标准化的问题/发现结构，适用于多种语言的报告"""
    language: str     # 语言，如 "python/cpp/java"
    slug: str         # 题目名
    description: str  # 题目描述
    constraints: str  # 数据范围限制
    buggy_code: str   # 出问题的代码
    bug_type: str         # bug类型
    bug_message: str  # bug信息
    fixed_code: str   # 修复后的代码

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __hash__(self):
        # 仅使用关键属性生成哈希值
        return hash((self.language, self.slug, self.description, self.constraints, self.buggy_code, self.bug_type, self.bug_message))

    def __eq__(self, other):
        return (
            isinstance(other, Issue)
            and self.language == other.language
            and self.slug == other.slug
            and self.description == other.description
            and self.constraints == other.constraints
            and self.buggy_code == other.buggy_code
            and self.bug_type == other.bug_type
            and self.bug_message == other.bug_message
        )

class MultiLangIssueAnalyzer:
    """
    接收多语言静态/动态工具输出的 JSON 报告，将其标准化。
    Agent 随后根据这些标准化的 Issue 来生成修复建议。
    """
    def __init__(self, logger=None, language="Unknown", type="General"):
        self.logger = logger
        self.language = language
        self.type = type

    def analyze_reports(self, json_reports: List[Dict | str], report_source_name: str = "Scan Report") -> List[Dict[str, Any]]:
        """
        接收一个或多个扫描报告（JSON 对象或字符串）列表，并提取标准化的 Issue。
        """
        all_issues: List[Issue] = []

        print(f"🚀 开始扫描 {len(json_reports)} 个报告文件...")

        for index, report in enumerate(json_reports, 1):
            if isinstance(report, str):
                try:
                    report = json.loads(report)
                except json.JSONDecodeError:
                    if self.logger:
                        self.logger.error(f"Failed to decode JSON report from {report_source_name}.")
                    continue
            
            # 解析当前这一个 JSON 报告
            issues = self._parse_custom_report(report)
            all_issues.extend(issues)

            # --- 新增：每处理完一个 JSON 报告输出一下 ---
            print(f"✅ [进度] 第 {index}/{len(json_reports)} 个 JSON 报告扫描完成 (本文件包含 {len(issues)} 个问题)")
            # ----------------------------------------

        # 删除重复项，并按文件和行号排序
        unique_issues = list(set(all_issues))
        return [i.to_dict() for i in sorted(unique_issues, key=lambda x: (x.slug))]
    
    def _detect_language(self, code: str) -> str:
        """
        基于特征的强力语言检测 (Regex 增强版)
        """
        if not code: 
            return "Unknown"
        
        # 0. 预处理：只取前 200 个字符判断，提高效率
        header = code[:500]

        # --- Python 特征 ---
        # 匹配: "class Solution:" 或 "class Solution(object):"
        if re.search(r'class\s+Solution.*:', header):
            return "python"
        # 匹配: "def func(self,"
        if re.search(r'def\s+\w+\s*\(.*self', header):
            return "python"
        # 匹配: Python 风格的 import 且没有分号结尾
        if "import " in header and ";" not in header and "from " in header:
            return "python"

        # --- C++ 特征 ---
        # 匹配: "#include <vector>" 等
        if "#include" in header or "using namespace std" in header:
            return "cpp"
        # 匹配: C++ 的 public: 访问修饰符 (带冒号)
        if "public:" in header:
            return "cpp"
        # 匹配: STL 容器特征
        if "vector<" in header or "string" in header and "->" in code:
            return "cpp"

        # --- Java 特征 ---
        # 匹配: "public class Solution"
        if re.search(r'public\s+class\s+\w+', header):
            return "java"
        # 匹配: Java 的方法签名 "public int method(" (注意没有冒号)
        if re.search(r'public\s+\w+\s+\w+\s*\(', header) and "public:" not in header:
            return "java"
        # 匹配: System.out
        if "System.out." in header:
            return "java"
        
        # --- 默认兜底 ---
        # 如果实在认不出来，但长得像 Python (缩进+冒号)，就猜 Python
        if ":" in header and "{" not in header and ";" not in header:
            return "python"

        return "Unknown"

    def _parse_custom_report(self, report: Dict) -> List[Issue]:
        """
        将 JSON 中的字典（每个问题的描述）转换为 Issue 对象，并进行鲁棒的类型检查。
        """
        parsed_issues: List[Issue] = []

        def process_single_item(item):
            if not isinstance(item, dict): 
                return None
            try:
                slug = item.get("slug", "UnknownSlug")
                description = item.get("description", "No description")
                constraints = item.get("constraints", "No constraints")
                buggy_code = item.get("buggy_code", "")

                # --- 1. 自动检测语言 ---
                # 如果 JSON 里没写，就调用 _detect_language 去猜
                detected_lang = item.get("lang") or item.get("language")
                if not detected_lang or detected_lang == "Unknown":
                    detected_lang = self._detect_language(buggy_code)
                
                # --- 2. 处理 Bug 类型 ---
                raw_type = item.get("type") or item.get("bug_type") or self.type
                bug_type_str = ", ".join(raw_type) if isinstance(raw_type, list) else str(raw_type)

                bug_message = item.get("explanations") or item.get("bug_message")
                
                # --- 3. 并发调用 AI (如果没有现有解释) ---
                if not bug_message:
                    bug_message = self.analyze_bug(slug, description, constraints, buggy_code)

                return Issue(
                    language=str(detected_lang), # 这里现在会有正确的值了 (如 "python")
                    slug=str(slug),
                    description=str(description),
                    constraints=str(constraints),
                    buggy_code=str(buggy_code),
                    bug_type=bug_type_str,
                    bug_message=str(bug_message),
                    fixed_code=""
                )
            except Exception as e:
                if self.logger: self.logger.warning(f"Parse error: {e}")
                return None

        # 使用线程池并发处理 (保留之前的提速优化)
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_item = {executor.submit(process_single_item, item): item for item in report}
            for future in as_completed(future_to_item):
                result = future.result()
                if result:
                    parsed_issues.append(result)
        
        return parsed_issues

    def analyze_bug(self, slug: str, description: str, constraints: str, buggy_code: str) -> str:
        """
        调用 AI 接口分析 buggy_code 中的 bug 并返回 bug 信息。
        (已增强网络稳定性和 Token 监控)
        """
        session = requests.Session()

        # 阿里云 DashScope 接口
        api_url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        
        # 务必确认这里已经替换成了你的真实 Key (去掉中文占位符)
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            return "Error: API Key missing"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        prompt_content = f"""
        Analyze the bug in this LeetCode problem solution.
        Problem: {slug}
        Description: {description}
        Constraints: {constraints}
        Buggy Code:
        ```
        {buggy_code}
        ```
        Please provide a short, one-sentence explanation of why this code is buggy.
        """

        payload = {
            "model": "qwen-turbo", 
            "messages": [
                {"role": "system", "content": "You are an expert code debugger. Be concise."},
                {"role": "user", "content": prompt_content}
            ],
            "temperature": 0.01
        }

        max_retries = 5
        
        for attempt in range(max_retries):
            try:
                # 每次请求前微小停顿
                # time.sleep(1)
                
                response = session.post(api_url, headers=headers, json=payload, timeout=30)
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        content = data['choices'][0]['message']['content']
                        
                        # --- 新增：Token 监控打印 ---
                        usage = data.get("usage", {})
                        total = usage.get("total_tokens", 0)
                        # 使用青色 (Cyan) 高亮打印，让你一眼就能看到
                        print(f"\033[96m   [Token监控] Bug分析 '{slug}' 消耗: {total} tokens\033[0m")
                        # --------------------------
                        
                        return content
                    except Exception:
                        return "Analysis format error"
                
                elif response.status_code == 429:
                    if self.logger:
                        self.logger.warning(f"⚠️ Rate limit (429). Cooling down 5s...")
                    time.sleep(5)
                    continue 
                
                else:
                    if self.logger:
                        self.logger.error(f"API Error {response.status_code}: {response.text}")
                    time.sleep(2)
                    continue

            except Exception as e:
                if self.logger:
                    self.logger.error(f"Request failed: {e}")
                time.sleep(2)
                continue
        
        return "Failed to analyze after retries"

        # # --- 增强的重试配置 ---
        # max_retries = 10       # 增加到 10 次
        # base_timeout = 60      # 基础超时 60 秒

        # for attempt in range(max_retries):
        #     try:
        #         # 每次请求前微小停顿，防止并发过高
        #         time.sleep(2)
                
        #         current_timeout = base_timeout + (attempt * 10)
                
        #         response = session.post(
        #             api_url, 
        #             headers=headers, 
        #             json=payload, 
        #             timeout=current_timeout
        #         )
                
        #         # 情况 1: 成功
        #         if response.status_code == 200:
        #             try:
        #                 data = response.json()
        #                 return data['choices'][0]['message']['content']
        #             except Exception:
        #                 return "Analysis format error"
                
        #         # 情况 2: 触发限流 (429)
        #         elif response.status_code == 429:
        #             wait_time = 30  # 强制冷却 30 秒
        #             if self.logger:
        #                 self.logger.warning(f"⚠️ Analyzer Rate limit (429). Cooling down {wait_time}s...")
        #             time.sleep(wait_time)
        #             continue 
                
        #         # 情况 3: 服务器错误
        #         elif response.status_code >= 500:
        #             time.sleep(5)
        #             continue

        #         else:
        #             if self.logger:
        #                 self.logger.error(f"API Error {response.status_code}: {response.text}")
        #             return f"Error analyzing code (HTTP {response.status_code})"

        #     except (requests.exceptions.ConnectionError, 
        #             requests.exceptions.ProxyError, 
        #             requests.exceptions.SSLError) as e:
        #         # 情况 4: 致命网络错误 (梯子断了)
        #         wait_time = 10 + (attempt * 5)
        #         if self.logger:
        #             self.logger.error(f"💥 Analyzer Network Error (attempt {attempt+1}): {e}")
        #             self.logger.info(f"⏳ Waiting {wait_time}s before retry...")
        #         time.sleep(wait_time)
        #         continue

        #     except Exception as e:
        #         if self.logger:
        #             self.logger.error(f"Request failed: {e}")
        #         time.sleep(5)
        #         continue
        
        # return "Failed to analyze after retries"