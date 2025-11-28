import os
import time
import requests
import re


class AutoFixer:
    def __init__(self, project_root, logger, api_key=None):
        self.project_root = project_root
        self.logger = logger
        # 从环境变量获取 Key，或者从 Scanner 传过来
        self.api_key = (
            api_key
            or os.getenv("DASHSCOPE_API_KEY")
        )

        # --- 以下是仅用于“稳定性优化”的参数，不改变业务逻辑 ---
        # 最多重试次数（包括第一次请求）
        self.max_retries = 8
        # 每次重试之间的基准等待时间（线性退避：delay * (attempt+1)）
        self.retry_delay = 3.0
        # 每次 HTTP 请求的超时时间（秒）
        self.timeout = 30
        # 可选：每次请求前 sleep 一小会儿，简单限流用（不需要可以设 0）
        self.per_request_delay = 2.0

    def apply_fix(self, issue) -> bool:
        """
        调用 LLM 修复代码，将结果存入 issue.fixed_code
        （保持原有逻辑不变）
        """
        self.logger.info(f"Fixing bug for {issue.slug}...")

        # 构造 Prompt（保持原样）
        prompt = f"""
        You are an expert code debugger.
        Language: {issue.language}
        Problem Description: {issue.description}
        Buggy Code:
        ```
        {issue.buggy_code}
        ```
        Error Type: {issue.bug_type}
        Error Message: {issue.bug_message}
        
        Please fix the code. Return ONLY the fixed code block enclosed in markdown ticks (```).
        Do not add explanations.
        """

        fixed_code = self._call_llm(prompt)

        if fixed_code:
            # 清理 markdown 标记
            clean_code = self._extract_code_block(fixed_code)
            issue.fixed_code = clean_code
            return True
        return False

    def _call_llm(self, prompt: str) -> str:
        session = requests.Session()
        api_url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "qwen-turbo",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.01,
        }

        max_retries = 5
        
        for attempt in range(max_retries):
            try:
                # 国内直连通常很快，不需要 sleep 很久，也不需要 verify=False
                response = session.post(
                    api_url,
                    headers=headers,
                    json=payload,
                    timeout=60
                )

                if response.status_code == 200:
                    try:
                        data = response.json()
                        
                        # --- 新增：Token 监控 (修复阶段) ---
                        usage = data.get("usage", {})
                        total = usage.get("total_tokens", 0)
                        p_tokens = usage.get("prompt_tokens", 0)
                        c_tokens = usage.get("completion_tokens", 0)
                        
                        # 我用了绿色 (\033[92m) 来打印，和扫描阶段的青色区分开
                        print(f"\033[92m   [Token监控] 修复代码生成消耗: {total} (Input:{p_tokens} + Output:{c_tokens})\033[0m")
                        # --------------------------------
                        
                        return data["choices"][0]["message"]["content"]
                    except Exception:
                        self.logger.error("JSON 解析失败")
                        return ""
                
                # 处理阿里云的限流 (429)
                elif response.status_code == 429:
                    self.logger.warning(f"Qwen Rate Limit (429), waiting 5s...")
                    time.sleep(5)
                    continue
                
                else:
                    self.logger.error(f"Qwen API Error: {response.status_code} - {response.text}")
                    return ""

            except Exception as e:
                self.logger.error(f"Request Error: {e}")
                time.sleep(2)
                continue
        
        return ""

        # # 参考 fixer/ai_client.py GroqClient 的思路，加上重试和退避
        # for attempt in range(self.max_retries):
        #     # 简单限流：每次请求前固定 sleep（可选）
        #     if self.per_request_delay > 0:
        #         time.sleep(self.per_request_delay)

        #     try:
        #         response = requests.post(
        #             api_url,
        #             headers=headers,
        #             json=payload,
        #             timeout=self.timeout,
        #         )
        #     except Exception as e:
        #         # 网络异常（超时、连接错误等）—— 记录日志并考虑重试
        #         self.logger.error(
        #             f"LLM Request error (attempt {attempt + 1}/{self.max_retries}): {e}"
        #         )
        #         # 如果还有重试机会，就等待一会儿再试
        #         if attempt < self.max_retries - 1:
        #             wait_time = self.retry_delay * (attempt + 1)
        #             self.logger.info(f"Retrying after {wait_time}s due to request error...")
        #             time.sleep(wait_time)
        #             continue
        #         # 重试用尽
        #         return ""

        #     # HTTP 状态码处理
        #     if response.status_code == 200:
        #         try:
        #             return response.json()["choices"][0]["message"]["content"]
        #         except Exception as e:
        #             # 返回结构异常
        #             self.logger.error(
        #                 f"LLM Response parse error: {e}, raw response: {response.text[:300]}"
        #             )
        #             return ""

        #     # 429 限流 or 5xx 服务端错误：认为是“可重试错误”
        #     if response.status_code in (429, 500, 502, 503, 504):
        #         self.logger.warning(
        #             f"LLM returned retryable status {response.status_code} "
        #             f"(attempt {attempt + 1}/{self.max_retries}). "
        #             f"body: {response.text[:200]}..."
        #         )
        #         if attempt < self.max_retries - 1:
        #             wait_time = self.retry_delay * (attempt + 1)
        #             self.logger.warning(f"Waiting {wait_time}s before retry...")
        #             time.sleep(wait_time)
        #             continue
        #         # 重试用尽
        #         self.logger.error(
        #             f"LLM Fix failed after retries: {response.status_code} - {response.text}"
        #         )
        #         return ""

        #     # 其它非 2xx 且不可重试的错误，直接返回失败
        #     self.logger.error(
        #         f"LLM Fix failed: HTTP {response.status_code} - {response.text}"
        #     )
        #     return ""

        # # 理论上不会走到这里（因为 return 已经在循环内处理），做个兜底
        # self.logger.error("LLM Fix failed: reached unexpected end of retry loop.")
        # return ""

    def _extract_code_block(self, text: str) -> str:
        # 提取 ```代码``` ，支持可选语言名 & \r\n 换行
        pattern = r"```(?:\w+)?\r?\n(.*?)```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            # 去掉前后空行/空白
            return match.group(1).strip()
        # 如果没有 markdown，直接返回原文（顺便 strip 一下更干净）
        return text.strip()
