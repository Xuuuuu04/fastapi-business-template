import hashlib
import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime

from shared.access.caller import SYSTEM, Caller


def validate_orgs(orgs: Sequence[str]) -> tuple[str, ...]:
    if len(set(orgs)) != len(orgs):
        raise ValueError("定时组织不能重复")
    if any(
        not org or org == "*" or org != org.strip() or len(org) > 64 or "\x00" in org
        for org in orgs
    ):
        raise ValueError("定时组织必须是明确的非空编号，最多64字符，不能使用通配符")
    return tuple(orgs)


def schedule_caller(org_id: str) -> Caller:
    return SYSTEM if org_id == "*" else replace(SYSTEM, org_id=org_id)


def period_key(name: str, org_id: str, slot: datetime) -> str:
    body = json.dumps([name, org_id, slot.isoformat()], ensure_ascii=False, separators=(",", ":"))
    return "schedule:" + hashlib.sha256(body.encode()).hexdigest()
