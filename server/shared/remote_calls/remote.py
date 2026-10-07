"""
外部系统的声明 remote() 和配置 RemoteConfig。
模块在代码中只写外部系统的名称和中文名；地址、密钥、超时写在配置 APP_REMOTES 中，
例如：APP_REMOTES={"supplier": {"base_url": "https://api.example.com/v1", "token": "..."}}
"""

from dataclasses import dataclass

from pydantic import BaseModel, Field, SecretStr


# 模块声明的外部系统，包含请求期限、并发与重试次数。
@dataclass(frozen=True, eq=False)
class Remote:
    name: str
    title: str
    timeout: float = 10.0
    concurrency: int = 8
    retries: int = 2


# 声明一个外部系统；name 与配置 APP_REMOTES 中的键对应。
def remote(
    name: str, title: str, *, timeout: float = 10.0, concurrency: int = 8, retries: int = 2
) -> Remote:
    return Remote(name, title, timeout, concurrency, retries)


# 外部系统的连接地址与访问密钥，由运行配置提供。
class RemoteConfig(BaseModel):
    base_url: str = Field(min_length=1, description="外部系统的基础地址")
    token: SecretStr | None = Field(default=None, description="访问密钥，不需要时留空")
    token_header: str = Field(default="Authorization", description="放密钥的请求头")
    token_prefix: str = Field(default="Bearer ", description="密钥前缀")
    timeout: float | None = Field(default=None, gt=0, description="覆盖代码中声明的超时秒数")
    max_response_bytes: int = Field(
        default=2_000_000, ge=1, le=256_000_000, description="实际解压后的响应字节上限"
    )
