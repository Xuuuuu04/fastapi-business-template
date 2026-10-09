# 接口和 worker 共用的镜像。在 server/ 目录构建：
#   docker build -f deploy/Dockerfile -t template-server .
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.9.28 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
COPY . .

FROM python:3.12-slim
# 内置PostgreSQL备份使用客户端工具，主版本必须与数据库一致（compose 中为 postgres:17）。
# 从 PostgreSQL 官方源安装指定主版本；数据库换版本时构建参数同步修改：--build-arg PG_MAJOR=16。
ARG PG_MAJOR=17
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update && apt-get install -y --no-install-recommends postgresql-client-${PG_MAJOR} \
    && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/* \
    && pg_dump --version | grep -q " ${PG_MAJOR}\." \
    && useradd --create-home --uid 10001 app
WORKDIR /app
COPY --from=build --chown=app:app /app /app
RUN mkdir -p /app/var/files /app/var/uploads && chown -R app:app /app/var
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 APP_ENV=production
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2)"]
CMD ["uvicorn", "app.setup.web:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--proxy-headers"]
