FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖（含 openssh-server 用于远程登录）
RUN apt-get update && apt-get install -y \
    pkg-config \
    default-libmysqlclient-dev \
    build-essential \
    openssh-server \
    && rm -rf /var/lib/apt/lists/*

# 配置 SSH：允许 root 密码登录
RUN mkdir /var/run/sshd \
    && sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config \
    && sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config \
    && sed -i 's/PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 创建媒体文件目录
RUN mkdir -p media/avatars media/bg_images

EXPOSE 3000 22

# 启动时：设置 SSH root 密码 → 启动 SSH → 迁移数据库 → 收集静态文件 → 启动 Gunicorn
# SSH_PASSWORD 通过 ClawCloud 环境变量注入（必填）
# SSH_USER / SSH_USER_PASSWORD 可选：创建普通用户（更安全）
CMD ["sh", "-c", \
     "echo \"root:${SSH_PASSWORD:-changeme}\" | chpasswd && \
      service ssh start && \
      python manage.py migrate --noinput && \
      python manage.py collectstatic --noinput --verbosity 0 && \
      gunicorn --bind 0.0.0.0:3000 --workers 2 --timeout 120 --access-logfile - backend.wsgi:application"]
