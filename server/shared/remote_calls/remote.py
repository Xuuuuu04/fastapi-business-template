from dataclasses import dataclass

from pydantic import BaseModel, Field, SecretStr


@dataclass(frozen=True, eq=False)
class Remote:
    name: str
    title: str
    timeout: float = 10.0
    concurrency: int = 8
    retries: int = 2


def remote(
    name: str, title: str, *, timeout: float = 10.0, concurrency: int = 8, retries: int = 2
) -> Remote:
    return Remote(name, title, timeout, concurrency, retries)


class RemoteConfig(BaseModel):
    base_url: str = Field(min_length=1, description="外部系统的基础地址")
    token: SecretStr | None = Field(default=None, description="访问密钥，不需要时留空")
    token_header: str = Field(default="Authorization", description="携带访问密钥的请求头名称")
    token_prefix: str = Field(default="Bearer ", description="密钥前缀")
    timeout: float | None = Field(
        default=None, gt=0, description="请求超时秒数；填写后替代代码中的 timeout 设置"
    )
    max_response_bytes: int = Field(
        default=2_000_000, ge=1, le=256_000_000, description="响应解压后允许读取的最大字节数"
    )
