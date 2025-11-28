import argparse
import sys
import json
import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv

# 引入我们刚才写的 SemgrepRunner
# 确保你已经创建了 src/scanner/semgrep_runner.py
from src.scanner.semgrep_runner import SemgrepRunner

# 1. 加载环境变量 (.env)
load_dotenv()

# 确定 run.py 所在的根目录
BASE_DIR = Path(__file__).parent

# =================================================================
# 关键配置: 确保 Python 能够找到 src 目录
# =================================================================
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# 导入引擎
try:
    from src.core.engine import BugFixEngine
except ImportError as e:
    print(f"❌ 严重错误：无法导入 src.core.engine ({e})", file=sys.stderr)
    print("请检查您的目录结构是否正确。", file=sys.stderr)
    sys.exit(1)


def load_benchmark_reports(benchmark_dir: Path) -> List[str]:
    """读取 benchmark 目录下的所有 JSON 报告文件的内容"""
    json_contents = []
    
    if not benchmark_dir.is_dir():
        print(f"❌ 错误: 基准测试目录未找到: {benchmark_dir.resolve()}", file=sys.stderr)
        return []
    
    print(f"🔍 [模式: Benchmark] 正在扫描目录: {benchmark_dir.name}")
    
    report_paths = list(benchmark_dir.glob("*.json"))
    
    if not report_paths:
        print("⚠️ 警告: 未找到任何 JSON 报告文件。", file=sys.stderr)
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
    parser = argparse.ArgumentParser(description="BugFixEngine v3.0 - AI 自动修复代理")
    
    parser.add_argument("--max-iterations", type=int, default=3, help="每个问题的最大修复尝试次数")
    
    # --- 新增参数：指定本地目录 ---
    parser.add_argument("--local-dir", type=str, help="[Semgrep模式] 指定要扫描的本地项目目录路径")
    # ---------------------------
    
    args = parser.parse_args()

    PROJECT_ROOT = str(BASE_DIR)
    
    # 检查 Key (友好的提示)
    if not os.getenv("DASHSCOPE_API_KEY"):
        print("⚠️  警告: .env 文件中未找到 DASHSCOPE_API_KEY，AI 修复功能可能无法工作！")

    # 初始化引擎
    print(f"⚙️  引擎初始化中...")
    engine = BugFixEngine(PROJECT_ROOT, max_iterations=args.max_iterations)
    
    json_reports_content = []

    # --- 核心逻辑分支 ---
    if args.local_dir:
        # === 分支 A: 扫描本地项目 (Semgrep 模式) ===
        local_path = Path(args.local_dir).resolve()
        if not local_path.exists():
            print(f"❌ 错误: 指定的本地目录不存在: {local_path}")
            sys.exit(1)
            
        print(f"🚀 [模式: Semgrep] 启动本地扫描: {local_path}")
        
        # 1. 调用 SemgrepRunner
        runner = SemgrepRunner()
        # 注意：这一步依赖环境变量里的 SEMGREP_APP_TOKEN (如果在 .env 里配了)
        scan_results = runner.scan_directory(str(local_path))
        
        if not scan_results:
            print("✨ Semgrep 未发现任何问题，或扫描出错。任务结束。")
            sys.exit(0)
            
        # 2. 桥接数据
        # engine.run 期望的是一个列表，里面每一项是一个报告
        # 我们把 scan_results (这是一个包含多个 bug 的字典列表) 作为一个“报告”传进去
        json_reports_content = [scan_results] 
        
    else:
        # === 分支 B: 跑 Benchmark (测试模式) ===
        BENCHMARK_DIR = BASE_DIR / "benchmark"
        json_reports_content = load_benchmark_reports(BENCHMARK_DIR)
        if not json_reports_content:
            print("❌ 未找到 Benchmark 报告，且未指定 --local-dir。无事可做。")
            sys.exit(1)

    # 3. 统一交给 Engine 处理
    # 无论数据来自 Semgrep 还是 Benchmark，Engine 都不需要知道，它只管修 Bug
    print(f"⚙️  开始处理任务流...")
    
    # 根据你的 engine.py，run 方法返回 5 个值
    try:
        fixed, failed, rpt_txt, rpt_json, issues = engine.run(json_reports=json_reports_content)

        # 退出码
        if failed > 0:
            sys.exit(1)
        else:
            sys.exit(0)
    except Exception as e:
        print(f"❌ 运行时发生未捕获异常: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()