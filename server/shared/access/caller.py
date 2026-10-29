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

    def can(self, permission: str) -> bool:
        if permission == PUBLIC or "*" in self.permissions:
            return True
        if permission == SIGNED_IN:
            return self.kind != "anonymous"
        module = permission.split(".", 1)[0]
        return permission in self.permissions or f"{module}.*" in self.permissions

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
