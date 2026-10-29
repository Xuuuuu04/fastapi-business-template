from shared.config.settings import Settings
from shared.jobs.health import worker_healthy


def main() -> None:
    settings = Settings()
    healthy = worker_healthy(settings.job_health_file, settings.job_health_seconds)
    raise SystemExit(0 if healthy else 1)


if __name__ == "__main__":
    main()
