"""
成员任务执行前核对剩余格式、组织流程与等待容量；完成回调复用worker的原事务。
"""

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.data.models import Data
from shared.errors.framework import StaleAttempt
from shared.jobs.tables import job_counts, jobs
from shared.pipelines.member_compat import group_compatible, member_compatible
from shared.pipelines.member_finish import finish
from shared.pipelines.member_store import member_for
from shared.pipelines.plan import FanOut, Pipeline, Stage, Wait
from shared.pipelines.schema import data_json
from shared.pipelines.storage import own, root_for
from shared.pipelines.tables import members, runs, stages

if TYPE_CHECKING:
    from shared.jobs.queue import JobQueue, Ticket


# worker只需allowed及finish，不理解成员规划、等待和汇合规则。
@dataclass
class MemberContext:
    queue: "JobQueue"
    ticket: "Ticket"
    root: dict
    parent: dict
    member: dict
    pipeline: Pipeline | None
    group: FanOut | None
    stage: Stage | None
    allowed: bool = True

    # 数据保存、子任务和外层下一阶段全部使用同一个业务提交事务。
    async def finish(self, connection: AsyncConnection, result: Data, run_id: str) -> None:
        assert self.group is not None and self.stage is not None
        await own(connection, self.ticket)
        root = await root_for(connection, self.root["id"])
        if root["current_stage"] != self.parent["name"] or root["state"] not in (
            "waiting_members",
            "running",
            "unknown",
            "version_blocked",
        ):
            raise StaleAttempt()
        parent = dict(
            (await connection.execute(select(stages).where(stages.c.id == self.parent["id"])))
            .mappings()
            .one()
        )
        body = data_json(
            self.stage.operation.output,
            result,
            self.parent["name"] + "/" + self.member["key"] + "/" + self.stage.name,
        )
        await finish(
            connection,
            self.queue,
            self.ticket,
            root,
            parent,
            self.member,
            self.group,
            self.stage,
            body,
            run_id,
        )


# 未登记成员不拥有流程语义，伪造专用键仍按普通任务处理。
async def prepare(queue: "JobQueue", ticket: "Ticket") -> MemberContext | None:
    async with queue.database.write() as connection:
        member = await member_for(connection, ticket.id)
        if member is None:
            return None
        await own(connection, ticket)
        root = await root_for(connection, member["pipeline_id"])
        member = await member_for(connection, ticket.id)
        if member is None:
            raise StaleAttempt()
        parent = dict(
            (await connection.execute(select(stages).where(stages.c.id == member["stage_id"])))
            .mappings()
            .one()
        )
        pipeline = queue.catalog.pipelines.get(root["pipeline"])
        group = (
            next((stage for stage in pipeline.stages if stage.name == parent["name"]), None)
            if pipeline
            else None
        )
        group = group if isinstance(group, FanOut) else None
        stage = (
            next((stage for stage in group.stages if stage.name == member["phase_name"]), None)
            if group
            else None
        )
        context = MemberContext(queue, ticket, root, parent, member, pipeline, group, stage)
        state, code, message = await decision(connection, context)
    if message:
        context.allowed = False
        await queue.fail(ticket, state, code, message, run_after=time.time() + 0.01)
    return context


# 已成功子阶段不比较；只在真正要执行的成员阶段及未来外层格式变化时暂停。
async def decision(connection: AsyncConnection, context: MemberContext) -> tuple[str, str, str]:
    root, parent, member, group, stage = (
        context.root,
        context.parent,
        context.member,
        context.group,
        context.stage,
    )
    if root["state"] not in ("waiting_members", "running"):
        return "blocked", "pipeline_inactive", "流程当前暂停成员执行"
    if parent["state"] == "joining":
        return "cancelled", "ratio_excluded", "成员未纳入已冻结的比例汇合，取消尚未开始的动作"
    if context.pipeline is None or group is None or stage is None:
        return "blocked", "member_declaration_missing", "成员阶段当前没有登记"
    if not group_compatible(
        root, group, context.pipeline, context.queue.catalog
    ) or not member_compatible(member, group, context.queue.catalog):
        return (
            "blocked",
            "member_schema_changed",
            f"成员{member['key']}阶段{member['phase_name']}或后续格式变化",
        )
    if isinstance(stage, Wait):
        if time.time() >= member["wait_until"]:
            return "failed", "member_wait_timeout", f"成员{member['key']}阶段{stage.name}等待超时"
        if not await wait_capacity(connection, context):
            return "waiting_retry", "member_wait_capacity", "等待成员检查容量"
    now = time.time()
    version = context.queue.catalog.binding(stage.operation).module.version
    member.update(started_at=now, module_version=version, attempt=context.ticket.attempt)
    await connection.execute(
        update(members)
        .where(members.c.id == member["id"])
        .values(
            state="running",
            started_at=now,
            module_version=version,
            attempt=context.ticket.attempt,
            error="",
            updated_at=now,
        )
    )
    return "", "", ""


# 同一等待子阶段跨组织受检查并发限制，容量不足时任务短暂重新排队。
async def wait_capacity(connection: AsyncConnection, context: MemberContext) -> bool:
    assert isinstance(context.stage, Wait)
    await connection.execute(
        select(job_counts.c.contract)
        .where(job_counts.c.contract == context.ticket.contract)
        .with_for_update()
    )
    count = await connection.scalar(
        select(func.count())
        .select_from(
            members.join(stages, members.c.stage_id == stages.c.id)
            .join(runs, members.c.pipeline_id == runs.c.id)
            .join(jobs, members.c.job_id == jobs.c.id)
        )
        .where(
            runs.c.pipeline == context.root["pipeline"],
            stages.c.name == context.parent["name"],
            members.c.phase_name == context.stage.name,
            members.c.state == "running",
            jobs.c.state == "running",
            jobs.c.lease_until > time.time(),
            jobs.c.id != context.ticket.id,
        )
    )
    return int(count or 0) < context.stage.max_parallel
