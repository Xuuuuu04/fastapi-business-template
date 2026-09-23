"""
读取并校验应用配置。
配置对象可以在测试中显式传入，导入文件时不读取环境。
"""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    name: str = "单体后端模板"
    db_path: Path = Path("var/app.db")
    write_key: SecretStr | None = None
    docs: bool = True
    monitor: bool = True
    monitor_key: SecretStr | None = None
    trace_limit: int = Field(default=1000, ge=1, le=100000)
    cors: list[str] = []
