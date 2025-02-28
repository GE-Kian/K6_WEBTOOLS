# 构建阶段
FROM python:3.9-slim as builder

# 设置构建参数
ARG DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 安装构建依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    gnupg2 \
    wget \
    pkg-config \
    default-libmysqlclient-dev && \
    rm -rf /var/lib/apt/lists/*

# 安装k6
RUN wget -q https://dl.k6.io/key.gpg && \
    gpg --no-default-keyring --keyring ./k6.gpg --import key.gpg && \
    gpg --no-default-keyring --keyring ./k6.gpg --export > /etc/apt/trusted.gpg.d/k6.gpg && \
    echo "deb https://dl.k6.io/deb stable main" | tee /etc/apt/sources.list.d/k6.list && \
    apt-get update && \
    apt-get install -y k6 && \
    rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

# 创建必要的目录
RUN mkdir -p scripts reports

# 复制应用代码
COPY . .

# 生产阶段
FROM python:3.9-slim

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 创建非root用户
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# 从构建阶段复制k6
COPY --from=builder /usr/bin/k6 /usr/bin/k6

# 设置工作目录
WORKDIR /app

# 从构建阶段复制应用
COPY --from=builder /app .
COPY --from=builder /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages

# 设置目录权限
RUN chown -R appuser:appgroup /app

# 切换到非root用户
USER appuser

# 添加健康检查
HEALTHCHECK --interval=30s --timeout=3s \
  CMD wget --quiet --tries=1 --spider http://localhost:8888/health || exit 1

# 暴露端口
EXPOSE 8888

# 启动应用
CMD ["python", "app.py"]