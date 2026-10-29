import hashlib
import secrets
from hmac import compare_digest

from pydantic import BaseModel, Field

from shared.access.caller import Caller


class ApiKeyConfig(BaseModel):
    name: str = Field(min_length=1, max_length=64, description="密钥名称，用于记录是谁调用")
    key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$", description="密钥原文的 SHA-256 摘要")
    permissions: list[str] = Field(default_factory=list, description="这把密钥拥有的权限")
    org_id: str = Field(default="", description="允许访问的组织编号；空值不能访问组织数据")


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def new_key() -> str:
    return secrets.token_urlsafe(32)


def find_caller(key: str, configs: list[ApiKeyConfig]) -> Caller | None:
    digest = hash_key(key)
    found = None
    for config in configs:
        if compare_digest(digest, config.key_sha256):
            found = config
    if found is None:
        return None
    return Caller(
        id=f"key:{found.name}",
        kind="service",
        name=found.name,
        permissions=frozenset(found.permissions),
        org_id=found.org_id,
    )


def current_caller(name: str, configs: list[ApiKeyConfig]) -> Caller | None:
    for config in configs:
        if config.name == name:
            return Caller(
                f"key:{name}", "service", name, frozenset(config.permissions), config.org_id
            )
    return None
