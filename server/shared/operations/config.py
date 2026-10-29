from urllib.parse import urlsplit

from pydantic import BaseModel, Field, SecretStr, model_validator


class OperationsConfig(BaseModel):
    backup: bool = False
    retention: bool = False
    capacity: bool = False
    notifications: bool = False
    backup_root: str = "var/backups"
    pg_bin: str = ""
    backup_days: int = Field(default=30, ge=1)
    backup_every_seconds: int = Field(default=86400, ge=60)
    retention_every_seconds: int = Field(default=3600, ge=60)
    check_every_seconds: int = Field(default=60, ge=10)
    batch_size: int = Field(default=500, ge=1, le=5000)
    run_days: int = Field(default=14, ge=1)
    job_days: int = Field(default=30, ge=1)
    audit_days: int = Field(default=90, ge=1)
    upload_days: int = Field(default=7, ge=1)
    original_days: int = Field(default=30, ge=1)
    original_prefixes: list[str] = []
    disk_percent: float = Field(default=90, gt=0, le=100)
    database_bytes: int = Field(default=0, ge=0)
    pause_noncritical: bool = False
    webhook_url: SecretStr | None = None
    webhook_format: str = Field(default="generic", pattern="^(generic|wecom|feishu)$")
    webhook_timeout: float = Field(default=10, gt=0, le=60)

    @model_validator(mode="after")
    def validate_targets(self) -> "OperationsConfig":
        if self.notifications and not self.webhook_url:
            raise ValueError("开启通知需要配置webhook_url")
        if self.webhook_url:
            url = urlsplit(self.webhook_url.get_secret_value())
            if url.scheme not in ("https", "http") or not url.hostname:
                raise ValueError("Webhook需要明确的HTTP或HTTPS目标")
        for prefix in self.original_prefixes:
            if (
                not prefix
                or prefix.startswith("/")
                or ".." in prefix
                or "\\" in prefix
                or "/" not in prefix.strip("/")
                or any(part in ("", ".") for part in prefix.split("/"))
            ):
                raise ValueError("原件保留仅接受相对安全前缀")
        return self

    def enabled(self) -> bool:
        return self.backup or self.retention or self.capacity or self.notifications
