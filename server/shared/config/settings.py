"""
读取并检查运行配置。环境变量统一以 APP_ 开头，示例见 server/.env.example。
导入本文件时不读取环境；测试可以直接传入 Settings(...)。
生产环境的额外要求在 check_production() 中检查，启动时不满足就拒绝运行。
"""

from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.access.keys import ApiKeyConfig
from shared.remote_calls.remote import RemoteConfig

LOCAL_JWT_SECRET = "local-development-only-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    env: Literal["local", "test", "production"] = "local"
    name: str = "单体后端模板"
    code_version: str = "dev"

    database_url: str = "sqlite+aiosqlite:///var/local.db"
    database_pool_size: int = Field(default=10, ge=1, le=200)
    database_wait_seconds: float = Field(default=10, gt=0, le=120)

    docs: bool = True
    cors: list[str] = []
    api_keys: list[ApiKeyConfig] = []
    dev_caller: bool = False
    max_body_bytes: int = Field(default=1_000_000, ge=1_000)
    max_inflight: int = Field(default=200, ge=1)

    run_records: Literal["memory", "database"] = "memory"
    run_record_limit: int = Field(default=2000, ge=10)
    run_record_buffer: int = Field(default=5000, ge=10)
    run_record_days: int = Field(default=14, ge=1)
    step_checks: bool | None = None

    model_base_url: str = ""
    model_api_key: SecretStr | None = None
    model_name: str = ""
    model_timeout: float = Field(default=60, gt=0)
    model_concurrency: int = Field(default=4, ge=1)
    model_keep_text: bool = False

    job_poll_seconds: float = Field(default=1.0, gt=0)
    job_concurrency: int = Field(default=4, ge=1)
    job_shutdown_seconds: float = Field(default=20, ge=0)

    remotes: dict[str, RemoteConfig] = {}
    legacy_database_url: str = ""
    cache_url: str = ""
    file_storage: Literal["local", "s3"] = "local"
    file_root: str = "var/files"
    upload_root: str = "var/uploads"
    upload_max_bytes: int = Field(default=10_000_000, ge=1)
    upload_suffixes: list[str] = [".txt", ".pdf", ".png", ".jpg", ".jpeg", ".csv"]
    upload_paths: list[str] = ["/api/v1/files/"]
    s3_bucket: str = ""
    s3_endpoint: str = ""
    s3_region: str = ""
    s3_access_key: str = ""
    s3_secret_key: SecretStr | None = None

    jwt_secret: SecretStr = SecretStr(LOCAL_JWT_SECRET)
    jwt_issuer: str = "backend-template"
    jwt_audience: str = "backend-template-api"
    token_minutes: int = Field(default=60, ge=1, le=1440)
    request_rate_per_minute: int = Field(default=120, ge=1)
    login_failure_limit: int = Field(default=5, ge=1)
    hsts_seconds: int = Field(default=0, ge=0)
    otel_endpoint: str = ""
    console: bool | None = None

    # 开发和测试环境默认开启额外的步骤检查，生产环境默认关闭以节省开销。
    def extra_step_checks(self) -> bool:
        if self.step_checks is not None:
            return self.step_checks
        return self.env != "production"

    # 判断是否配置了真实的大模型服务。
    def has_model(self) -> bool:
        return bool(self.model_base_url and self.model_name and self.model_api_key)

    # 本地与测试默认显示诊断页，生产环境默认关闭。
    def console_enabled(self) -> bool:
        return self.console if self.console is not None else self.env != "production"


# 列出生产环境配置中不允许的地方。
def check_production(settings: Settings) -> list[str]:
    if settings.env != "production":
        return []
    problems = []
    if not settings.database_url.startswith("postgresql"):
        problems.append("生产环境必须使用 PostgreSQL（APP_DATABASE_URL 以 postgresql 开头）")
    if settings.dev_caller:
        problems.append("生产环境不能开启 APP_DEV_CALLER")
    if settings.run_records != "database":
        problems.append("生产环境的运行记录必须保存到数据库（APP_RUN_RECORDS=database）")
    if not settings.api_keys:
        problems.append("生产环境至少需要配置一把服务密钥（APP_API_KEYS）")
    if settings.code_version == "dev":
        problems.append("生产环境需要写入部署的代码版本（APP_CODE_VERSION，一般是 git 提交号）")
    secret = settings.jwt_secret.get_secret_value()
    if secret == LOCAL_JWT_SECRET or len(secret) < 32:
        problems.append("生产环境必须设置独立的 APP_JWT_SECRET，至少 32 个字符")
    return problems
