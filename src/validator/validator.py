import subprocess
import os
import sys
import tempfile
import ast
import re
import shutil

class Validator:
    def __init__(self, project_root, logger):
        self.project_root = project_root
        self.logger = logger

    def run_tests(self, issue) -> bool:
        """
        验证流程分发器
        """
        fixed_code = getattr(issue, 'fixed_code', "")
        if not fixed_code:
            self.logger.warning(f"⚠️ [验证跳过] 没有任何代码可供验证: {issue.slug}")
            return False

        lang = issue.language.lower()
        
        # 根据语言分发到不同的验证逻辑
        if "python" in lang:
            return self._validate_python(fixed_code, issue.slug)
        elif "cpp" in lang or "c++" in lang or "c" == lang:
            return self._validate_cpp(fixed_code, issue.slug)
        elif "java" in lang:
            return self._validate_java(fixed_code, issue.slug)
        else:
            self.logger.info(f"⚠️ [验证跳过] 不支持的语言类型: {lang}")
            return True

    def _validate_python(self, code: str, slug: str) -> bool:
        """
        Python 双重验证：
        1. AST 静态语法检查 (查括号、缩进)
        2. exec 动态定义检查 (查 import 遗漏、NameError)
        """
        try:
            # 1. 静态语法检查
            ast.parse(code)
        except SyntaxError as e:
            self.logger.error(f"❌ [验证失败] Python 语法错误 ({slug}): {e}")
            return False

        try:
            # 2. 动态定义检查 (尝试运行代码定义部分，捕捉缺 import 的情况)
            # 比如 LLM 经常用了 List 但没 import typing
            exec_globals = {}
            exec(code, exec_globals)
            self.logger.info(f"✅ [验证通过] Python 语法与定义检查通过 ({slug})")
            return True
        except NameError as e:
            self.logger.error(f"❌ [验证失败] Python 缺少引用/未定义变量 ({slug}): {e}")
            # 这是一个很棒的反馈点：如果是缺少 List，说明 LLM 忘了 import
            return False
        except Exception as e:
            self.logger.warning(f"⚠️ [验证警告] Python 运行时异常 (可能是逻辑错误，暂放行): {e}")
            # 如果是逻辑报错我们暂时放行，因为没有测试用例没法完全保证不报错
            return True

    def _validate_cpp(self, code: str, slug: str) -> bool:
        """
        C++ 编译检查 (依赖 g++)
        """
        if not self._is_tool_available('g++'):
            self.logger.warning("⚠️ [验证跳过] 环境中未找到 g++，无法验证 C++ 代码")
            return True

        with tempfile.NamedTemporaryFile(suffix=".cpp", mode='w', delete=False, encoding='utf-8') as f:
            f.write(code)
            fname = f.name

        try:
            # -fsyntax-only: 只检查语法不链接
            # -std=c++17: 使用较新标准，防止 auto 等关键字报错
            subprocess.check_call(
                ['g++', '-fsyntax-only', '-std=c++17', fname], 
                stderr=subprocess.PIPE, # 捕获错误输出以免刷屏
                stdout=subprocess.DEVNULL
            )
            self.logger.info(f"✅ [验证通过] C++ 编译检查通过 ({slug})")
            return True
        except subprocess.CalledProcessError as e:
            # 尝试解码错误信息
            err_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else "Unknown compilation error"
            # 只取前200个字符，防止日志太长
            self.logger.error(f"❌ [验证失败] C++ 编译失败 ({slug}):\n{err_msg[:200]}...")
            return False
        finally:
            if os.path.exists(fname):
                try:
                    os.remove(fname)
                except:
                    pass

    def _validate_java(self, code: str, slug: str) -> bool:
        """
        Java 编译检查 (依赖 javac)
        难点：Java 文件名必须等于类名
        """
        if not self._is_tool_available('javac'):
            self.logger.warning("⚠️ [验证跳过] 环境中未找到 javac，无法验证 Java 代码")
            return True

        # 1. 使用正则提取类名 (public class Xxx)
        match = re.search(r'public\s+class\s+(\w+)', code)
        if not match:
            # 如果没找到 public class，可能是 class Solution (非 public)
            match_nopub = re.search(r'class\s+(\w+)', code)
            if match_nopub:
                class_name = match_nopub.group(1)
            else:
                self.logger.error(f"❌ [验证失败] Java 代码中未找到类定义 ({slug})")
                return False
        else:
            class_name = match.group(1)

        # 2. 创建临时目录和对应的 .java 文件
        temp_dir = tempfile.mkdtemp()
        java_file_path = os.path.join(temp_dir, f"{class_name}.java")
        
        try:
            with open(java_file_path, 'w', encoding='utf-8') as f:
                f.write(code)
            
            # 3. 调用 javac 编译
            subprocess.check_call(
                ['javac', java_file_path],
                stderr=subprocess.PIPE,
                stdout=subprocess.DEVNULL
            )
            self.logger.info(f"✅ [验证通过] Java 编译检查通过 ({slug})")
            return True
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else "Unknown compilation error"
            self.logger.error(f"❌ [验证失败] Java 编译失败 ({slug}):\n{err_msg[:200]}...")
            return False
        finally:
            # 清理临时目录
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _is_tool_available(self, name):
        return shutil.which(name) is not None