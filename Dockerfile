# 1. 选择基础镜像：使用官方轻量级 Python 3.9 (基于 Linux Debian)
FROM python:3.11-slim

# 2. 设置工作目录 (容器内的文件夹)
WORKDIR /app

# 3. 安装系统级依赖
# 我们需要: 
# - git (semgrep可能需要)
# - g++ (为了跑 validator.py 里的 C++ 验证)
# - default-jdk (为了跑 validator.py 里的 Java 验证)
RUN apt-get update && apt-get install -y \
    git \
    g++ \
    default-jdk \
    && rm -rf /var/lib/apt/lists/*

# 4. 复制依赖清单并安装 Python 库
# (假设你根目录有 requirements.txt，如果没有，手动 pip install 也行)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# 强制再装一次 semgrep，确保它在 Linux 环境下安装正确
RUN pip install semgrep

# 5. 把当前项目的所有代码复制进容器
COPY . .

# 6. 设置环境变量 (防止 Python 生成 pyc 垃圾文件)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 7. 默认启动命令 (只打印帮助，具体运行我们在命令行指定)
CMD ["python", "run.py", "--help"]