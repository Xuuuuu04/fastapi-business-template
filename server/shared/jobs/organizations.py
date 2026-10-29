import hashlib
import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.access.caller import SYSTEM, Caller
from shared.jobs.submission import scope_for
from shared.jobs.tables import jobs


def validate_orgs(orgs: Sequence[str]) -> tuple[str, ...]:
    if len(set(orgs)) != len(orgs):
        raise ValueError("定时组织不能重复")
    if any(
        not org or org == "*" or org != org.strip() or len(org) > 64 or "\x00" in org
        for org in orgs
    ):
        raise ValueError("定时组织必须是明确的非空编号，最多64字符，不能使用通配符")
    return tuple(orgs)


def configured_orgs(org_id: str, org_ids: Sequence[str]) -> tuple[str, ...]:
    selected = validate_orgs(org_ids)
    if org_id:
        validate_orgs((org_id,))
        if selected and org_id not in selected:
            raise ValueError("schedule_org_id 必须属于 schedule_org_ids")
        return selected or (org_id,)
    return selected


def schedule_caller(org_id: str) -> Caller:
    return SYSTEM if org_id == "*" else replace(SYSTEM, org_id=org_id)


def period_key(name: str, org_id: str, slot: datetime) -> str:
    if org_id == "*":
        return f"schedule:{name}:{slot.isoformat()}"
    body = json.dumps([name, org_id, slot.isoformat()], ensure_ascii=False, separators=(",", ":"))
    return "schedule:org:" + hashlib.sha256(body.encode()).hexdigest()


async def legacy_exists(
    connection: AsyncConnection, name: str, contract: str, org_id: str, slot: datetime
) -> bool:
    row = (
        await connection.execute(
            select(jobs.c.caller_json).where(
                jobs.c.contract == contract,
                jobs.c.key_scope.in_((SYSTEM.id, scope_for(schedule_caller(org_id)))),
                jobs.c.key == f"schedule:{name}:{slot.isoformat()}",
            )
        )
    ).first()
    return row is not None and json.loads(row.caller_json).get("org_id") == org_id
