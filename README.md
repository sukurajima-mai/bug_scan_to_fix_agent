# **🚀 BugFixEngine: Intelligent Automated Code Repair Agent**

**BugFixEngine** 是一个基于 AI Agent 的自动化代码修复系统，专为批量修复 GitHub/LeetCode 风格的算法代码缺陷而设计。

区别于传统的静态分析工具，本系统采用 **Agentic Workflow（智能体工作流）**，结合 **LLM（大语言模型）** 的语义理解能力与 **AST/Compiler（编译器）** 的验证能力，实现了从“缺陷感知”到“代码修复”再到“有效性验证”的全流程闭环。

## **✨ 核心特性 (Key Features)**

* **⚡ 高并发流水线**：采用 ThreadPoolExecutor 并发扫描架构，结合生产-消费者模式，将单文件处理耗时从 **8 分钟压缩至 30 秒**。  
* **🛡️ 鲁棒的网络调度**：内置指数退避（Exponential Backoff）重试机制，自动处理 API 限流 (429) 和网络波动，支持 **50+ 大文件零中断运行**。  
* **🧠 混合模型策略 (Tiered Inference)**：  
  * **Scanner**: 使用 Qwen-Turbo 进行极速并发扫描与元数据提取。  
  * **Fixer**: 使用 Qwen-Plus 进行深度逻辑推理与代码重写。  
* **🔍 智能语言感知**：针对缺失元数据的输入，基于正则特征工程（Regex Feature Engineering）自动识别 **Python / Java / C++** 代码。  
* **✅ 强验证机制**：  
  * **Python**: AST 语法树解析 \+ exec() 沙箱预执行（拦截 Missing Import）。  
  * **C++/Java**: 子进程真实调用 g++/javac 进行编译验证，杜绝幻觉代码。

## **🏗️ 系统架构 (Architecture)**

系统采用 **流水线式协作 (Pipeline-based Collaboration)** 架构，解耦为三个核心智能实体：

graph LR  
    A\[Input Reports\] \--\> B(Analyzer Agent);  
    B \--\>|Concurrent Scan| C{Issue Queue};  
    C \--\> D(Fixer Agent);  
    D \--\>|LLM Generation| E\[Draft Code\];  
    E \--\> F(Validator Agent);  
    F \--\>|Compiler/AST Check| G{Pass?};  
    G \-- Yes \--\> H\[Final Report\];  
    G \-- No \--\> D;

1. **Analyzer (感知层)**: 多线程读取报告，自动补全语言类型，提取 Bug 上下文。  
2. **Fixer (决策层)**: 动态构建 Prompt，根据错误类型调用 LLM 生成修复方案。  
3. **Validator (执行层)**: 调用本地工具链进行静态/动态验证，确保修复有效性。

## **📊 性能表现 (Performance)**

基于 186 个真实 LeetCode 缺陷样本的测试数据：

| 指标 | v1.0 (串行脚本) | v3.0 (当前版本) | 提升幅度 |
| :---- | :---- | :---- | :---- |
| **单文件耗时** | \~480s | **\~30s** | 🚀 **16x** |
| **修复成功率** | \< 30% | **66.1%** | 📈 **2.2x** |
| **语言识别率** | 0% (Unknown) | **99.9%** | ✅ 精准 |

## **🚀 快速开始 (Quick Start)**

### **1\. 环境准备**

确保已安装 Python 3.9+ 以及 GCC/Java 环境（用于验证 C++/Java 代码）。

\# 克隆仓库  
git clone \[https://github.com/YourUsername/BugFixEngine.git\](https://github.com/YourUsername/BugFixEngine.git)  
cd BugFixEngine

\# 安装依赖  
pip install \-r requirements.txt

### **2\. 配置 API Key**

本项目默认支持阿里云 DashScope (Qwen) 模型。请在环境变量中设置 Key，或修改 src/core/engine.py (不推荐)。

**Linux/Mac:**

export DASHSCOPE\_API\_KEY="sk-your-api-key"

**Windows (PowerShell):**

$env:DASHSCOPE\_API\_KEY="sk-your-api-key"

### **3\. 运行修复**

将待修复的 JSON 报告放入 benchmark/ 目录中，然后运行：

\# 默认运行（并发度 10，最大重试 3 次）  
python run.py

\# 指定最大迭代次数  
python run.py \--max-iterations 5

### **4\. 查看报告**

运行完成后，结果将生成在 reports/ 目录下，包含：

* bug\_fix\_report.md: 易读的 Markdown 汇总报告。  
* bug\_fix\_report.json: 结构化的详细数据。

## **📂 项目结构 (Project Structure)**

BugFixEngine/  
├── benchmark/              \# \[输入\] 待修复的 JSON 缺陷报告  
├── reports/                \# \[输出\] 生成的修复报告 (自动按时间戳归档)  
├── src/                    \# 核心源码  
│   ├── analyzer/           \# 包含分类器与特征识别  
│   ├── core/               \# Engine 主引擎逻辑  
│   ├── fixer/              \# AutoFixer (LLM 调用与重试逻辑)  
│   ├── reporter/           \# 报告生成器  
│   ├── scanner/            \# 多线程扫描器  
│   └── validator/          \# AST 与编译器验证器  
├── run.py                  \# 项目启动入口  
├── requirements.txt        \# 依赖列表  
└── README.md               \# 项目文档

## **🤝 贡献 (Contributing)**

欢迎提交 Issue 和 PR！  
目前的 TODO List:

* \[ \] 引入 RAG 检索增强，基于历史修复案例优化 Prompt。  
* \[ \] 增加 Docker 支持，统一 C++/Java 的编译环境。  
* \[ \] 支持更多静态扫描工具 (如 Semgrep) 的输入格式。

## **📄 License**

MIT License. See [LICENSE](https://www.google.com/search?q=LICENSE) file for details.