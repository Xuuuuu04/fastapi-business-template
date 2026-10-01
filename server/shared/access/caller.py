"""
定义调用者身份和权限判断。
身份来自已验证的密钥或登录结果，不能来自请求体自报的内容。
权限名写作“模块名.动作”，例如 file_library.write；“模块名.*”表示该模块的全部权限。
public 对所有调用者开放；signed_in 对任何已登录的用户、服务密钥和系统任务开放，例如修改自己的密码。
"""

from dataclasses import dataclass, field
from typing import Literal

PUBLIC = "public"
SIGNED_IN = "signed_in"

CallerKind = Literal["user", "service", "system", "developer", "anonymous"]


@dataclass(frozen=True)
class Caller:
    id: str
    kind: CallerKind
    name: str
    permissions: frozenset[str] = field(default_factory=frozenset)
    org_id: str = ""

    # 判断调用者是否拥有某项权限；PUBLIC 对所有调用者开放。
    def can(self, permission: str) -> bool:
        if permission == PUBLIC or "*" in self.permissions:
            return True
        if permission == SIGNED_IN:
            return self.kind != "anonymous"
        module = permission.split(".", 1)[0]
        return permission in self.permissions or f"{module}.*" in self.permissions

    # 转成可以保存在任务表里的最小身份信息，不含任何凭据。
    def to_record(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "permissions": sorted(self.permissions),
            "org_id": self.org_id,
        }


ANONYMOUS = Caller("anonymous", "anonymous", "匿名访问")
SYSTEM = Caller("system", "system", "系统定时任务", frozenset({"*"}), "*")
DEVELOPER = Caller("developer", "developer", "本地开发者", frozenset({"*"}), "*")


# 从任务表保存的身份信息恢复调用者。
def caller_from_record(record: dict[str, object]) -> Caller:
    permissions = record.get("permissions", [])
    names = permissions if isinstance(permissions, list) else []
    kind = str(record.get("kind", "anonymous"))
    allowed: tuple[CallerKind, ...] = ("user", "service", "system", "developer", "anonymous")
    return Caller(
        id=str(record.get("id", "")),
        kind=kind if kind in allowed else "anonymous",
        name=str(record.get("name", "")),
        permissions=frozenset(str(name) for name in names),
        org_id=str(record.get("org_id", "")),
    )
