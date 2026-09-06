"""Linux 生产 ASGI 进程配置；超时覆盖现有 180 秒 SSE 流的排空时间。"""

import os

bind = "0.0.0.0:8000"
worker_class = "uvicorn_worker.UvicornWorker"
workers = int(os.getenv("WEB_CONCURRENCY", "2"))
timeout = 240
graceful_timeout = 210
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
# 不让 Uvicorn 无条件信任任意来源的客户端 IP / 协议头。
# Django 显式读取宿主机 Nginx 重写的 X-Forwarded-Proto。
forwarded_allow_ips = os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1")
