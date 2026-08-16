FROM python:3.13-slim

# 时区设为上海，保证 cron 按本地时间运行
ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends cron tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 建立必要目录并装入 crontab
RUN mkdir -p /app/logs /app/data /app/reports \
    && crontab /app/crontab

# 前台运行 cron 守护进程；容器存活即持续按计划执行
ENTRYPOINT ["cron", "-f"]
