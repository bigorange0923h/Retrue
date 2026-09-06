FROM python:3.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings_production \
    LOG_TO_FILE=false

WORKDIR /app
COPY requirements.txt requirements-production.txt ./
RUN pip install --no-cache-dir -r requirements-production.txt

# psycopg[binary] 自带 libpq；无需安装编译器和数据库服务。
RUN groupadd --gid 10001 retrue \
    && useradd --uid 10001 --gid retrue --no-create-home --shell /usr/sbin/nologin retrue \
    && mkdir -p /app/staticfiles /app/media \
    && chown retrue:retrue /app/staticfiles /app/media
COPY --chown=root:root . .

USER 10001:10001
EXPOSE 8000
# 迁移和 collectstatic 由发布者明确执行，重启只启动服务。
CMD ["gunicorn", "--config", "gunicorn.conf.py", "config.asgi:application"]
