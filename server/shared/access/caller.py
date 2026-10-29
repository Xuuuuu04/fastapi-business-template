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


CALLER_KINDS: tuple[CallerKind, ...] = ("user", "service", "system", "developer", "anonymous")
RECORD_KEYS = {"id", "kind", "name", "permissions", "org_id"}


def caller_from_record(record: dict[str, object]) -> Caller:
    if set(record) != RECORD_KEYS:
        raise ValueError(f"调用者记录必须正好包含这些字段：{'、'.join(sorted(RECORD_KEYS))}")
    identity, name, org_id = record["id"], record["name"], record["org_id"]
    if not (isinstance(identity, str) and isinstance(name, str) and isinstance(org_id, str)):
        raise ValueError("调用者记录的 id、name、org_id 必须是文字")
    permissions = record["permissions"]
    if not isinstance(permissions, list) or not all(isinstance(item, str) for item in permissions):
        raise ValueError("调用者记录的 permissions 必须是文字列表")
    kind = next((item for item in CALLER_KINDS if item == record["kind"]), None)
    if kind is None:
        raise ValueError(f"调用者记录的 kind 无效：{record['kind']}")
    return Caller(identity, kind, name, frozenset(permissions), org_id)
