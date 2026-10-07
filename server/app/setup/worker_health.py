"""
检查本容器 worker 最近的正常循环：python -m app.setup.worker_health。
只读取临时信号文件，不访问数据库，不把接口服务健康当作 worker 健康。
"""

from shared.config.settings import Settings
from shared.jobs.health import worker_healthy


# 返回健康检查退出码，供容器判断近期循环状态。
def main() -> None:
    settings = Settings()
    healthy = worker_healthy(settings.job_health_file, settings.job_health_seconds)
    raise SystemExit(0 if healthy else 1)


if __name__ == "__main__":
    main()
