import argparse
import sys
import json
import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv

load_dotenv()

# 确定 run.py 所在的根目录
BASE_DIR = Path(__file__).parent

# =================================================================
# 关键修复: 确保 Python 能够找到 src 目录作为顶级包。
# 我们将 BASE_DIR 本身添加到路径中，这样 Python 就能解析 'src.core.engine'
# =================================================================
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# 现在可以安全地导入了
try:
    from src.core.engine import BugFixEngine
except ImportError as e:
    print(f"❌ 严重错误：无法导入 src.core.engine ({e})", file=sys.stderr)
    print("请检查您的目录结构是否为：\n- run.py\n- src/\n- benchmark/", file=sys.stderr)
    sys.exit(1)


def load_benchmark_reports(benchmark_dir: Path) -> List[str]:
    """读取 benchmark 目录下的所有 JSON 报告文件的内容"""
    json_contents = []
    
    if not benchmark_dir.is_dir():
        print(f"❌ 错误: 基准测试目录未找到: {benchmark_dir.resolve()}", file=sys.stderr)
        return []
    
    print(f"🔍 正在扫描基准测试目录: {benchmark_dir.name}")
    
    report_paths = list(benchmark_dir.glob("*.json"))
    
    if not report_paths:
        print("⚠️ 警告: 未找到任何 JSON 报告文件。请确保您的 JSON 文件在正确位置。", file=sys.stderr)
        return []
        
    print(f"📄 找到 {len(report_paths)} 个报告文件。")

    for path in report_paths:
        try:
            content = path.read_text(encoding='utf-8')
            json_contents.append(content)
        except Exception as e:
            print(f"❌ 读取文件 {path.name} 错误: {e}", file=sys.stderr)
            
    return json_contents


def main():
    parser = argparse.ArgumentParser(description="Bug Auto Fix Agent v3.0 (代码片段基准测试模式)")
    parser.add_argument("--max-iterations", type=int, default=3, help="每个问题的最大修复尝试次数")
    args = parser.parse_args()

    PROJECT_ROOT = str(BASE_DIR)
    BENCHMARK_DIR = BASE_DIR / "benchmark"
    
    # 增加一个友好的检查
    if not os.getenv("DASHSCOPE_API_KEY"):
        print("⚠️  警告: 未找到 DASHSCOPE_API_KEY 环境变量，请检查 .env 文件！")
    
    # 1. 加载 JSON 报告内容
    json_reports_content = load_benchmark_reports(BENCHMARK_DIR)
    if not json_reports_content:
        sys.exit(1)

    # 2. 初始化引擎
    print(f"⚙️  初始化引擎，报告将输出至: {PROJECT_ROOT}")
    engine = BugFixEngine(PROJECT_ROOT, max_iterations=args.max_iterations)
    
    # 3. 运行引擎
    fixed, failed, rpt_txt, rpt_json = engine.run(json_reports=json_reports_content)

    # 退出码反馈
    if failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()