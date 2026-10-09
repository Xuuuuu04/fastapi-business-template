"""
内置运维也用Module/Flow/JobPlan/Schedule声明，进入检查、计算图和运行图。
"""

from datetime import timedelta
from typing import Any

from sqlalchemy import exists, select

from shared.data.fields import meaning
from shared.data.models import Data, WorkData
from shared.db.access import Db
from shared.flow.flow import Flow
from shared.flow.step import step
from shared.jobs.checkpoint import Checkpoint
from shared.jobs.plan import JobPlan, Schedule
from shared.jobs.tables import jobs
from shared.modules.contract import contract
from shared.modules.module import Module
from shared.operations import capacity, retention
from shared.operations.backup import Verify, backup
from shared.operations.notifications import Channel, Webhook, deliver, enqueue
from shared.operations.tables import state
from shared.pipelines.tables import notifications


# 定时运维没有业务输入，处理范围来自经过校验的配置。
class Input(Data):
    pass


# 运维事实输出，失败不能误称已备份。
class Result(Data):
    details: dict[str, Any] = meaning("实际运维结果，备份verified=false代表失败")


# 运维步骤共享结果。
class Work(WorkData):
    result: Result = meaning("实际结果")


# 清理恢复游标保持固定截止和阶段。
class Cursor(Data):
    phase: int = meaning("清理阶段", default=0)
    cutoff: float = meaning("本次固定清理截止时刻", default=0)
    batch: int = meaning("已经提交清理批次数", default=0)


# 配置与恢复回调由组装入口绑定，步骤内只使用本模块存储。
class Store:
    # 绑定框架事务和明确配置。
    def __init__(self, db: Db, settings: Any, verify: Verify, channel: Channel) -> None:
        self.db, self.settings, self.verify, self.channel = db, settings, verify, channel

    # 捕获备份失败为明确结果，后续保存提醒事实。
    async def backup(self) -> dict[str, Any]:
        try:
            return await backup(self.settings, self.verify)
        except Exception as error:
            return dict(verified=False, error=type(error).__name__)

    # 保存失败提醒，不把验证失败归档当成功。
    async def record_backup(self, result: dict[str, Any]) -> None:
        if not result["verified"]:
            import time

            await enqueue(self.db, "backup_failed", str(int(time.time())), result)

    # 观察容量并更新共享领取条件。
    async def capacity(self) -> dict[str, Any]:
        result = await capacity.observe(self.db, self.settings)
        await capacity.save(self.db, self.settings, result)
        return result

    # 扫描待确认任务并投递一条提醒。
    async def notify(self) -> int:
        rows = await self.db.all(
            select(jobs.c.id, jobs.c.state, jobs.c.contract)
            .where(
                jobs.c.state.in_(("unknown", "blocked")),
                ~exists(
                    select(notifications.c.id).where(
                        notifications.c.kind == "confirmation", notifications.c.key == jobs.c.id
                    )
                ),
            )
            .limit(self.settings.operations.batch_size)
        )
        for row in rows:
            await enqueue(self.db, "confirmation", row["id"], dict(row))
        return await deliver(self.db, self.channel)

    # 按当前清理阶段处理一批。
    async def clean(self, phase: str, cutoff: float) -> int:
        if phase in ("uploads", "originals"):
            return await retention.clean_files(self.settings, phase, cutoff)
        return await retention.clean_db(self.db, phase, cutoff, self.settings.operations)


# 重型备份在业务写入事务之前完成。
@step("数据库和文件备份并隔离恢复校验", writes=["result"])
async def take_backup(data: Work, store: Store) -> None:
    data.result = Result(details=await store.backup())


# 失败输出和提醒一起保存。
@step("记录备份失败提醒", reads=["result"], saves=True)
async def backup_outcome(data: Work, store: Store) -> None:
    await store.record_backup(data.result.details)


# 容量事实进入运行图。
@step("容量检查与非关键任务暂停事实", writes=["result"], saves=True)
async def check_capacity(data: Work, store: Store) -> None:
    data.result = Result(details=await store.capacity())


# 提醒失败保留pending供后续尝试。
@step("登记待确认提醒并投递一条通知", writes=["result"], saves=True)
async def send_notification(data: Work, store: Store) -> None:
    data.result = Result(details={"processed": await store.notify()})


# 每段短事务提交后才推进游标。
@step("按固定截止分段清理", writes=["result"], saves=True)
async def clean_batch(data: Work, store: Store, checkpoint: Checkpoint) -> None:
    phase, cutoff = retention.initial_cursor(checkpoint.cursor)
    rows = await store.clean(retention.PHASES[phase], cutoff)
    data.result = Result(details={"phase": retention.PHASES[phase], "rows": rows})
    if rows < store.settings.operations.batch_size:
        phase += 1
    cursor = {"phase": phase, "cutoff": cutoff, "batch": int(checkpoint.cursor.get("batch", 0)) + 1}
    if phase == len(retention.PHASES):
        checkpoint.finish(rows=rows, cursor=cursor)
    else:
        checkpoint.advance(cursor, rows=rows)


backup_op = contract(
    "system_ops.backup", "备份与恢复验证", input=Input, output=Result, access="system_ops.run"
)
retention_op = contract(
    "system_ops.retention", "分段数据保留", input=Input, output=Result, access="system_ops.run"
)
capacity_op = contract(
    "system_ops.capacity", "容量观察", input=Input, output=Result, access="system_ops.run"
)
notify_op = contract(
    "system_ops.notify", "提醒投递", input=Input, output=Result, access="system_ops.run"
)


# 所有运维计划固定系统组织，避免按每个产品组织重复整库备份/清理。
def make_module(settings: Any, verify: Verify, channel: Channel | None = None) -> Module:
    config = settings.operations
    definitions = [
        (config.backup, backup_op, [take_backup, backup_outcome], config.backup_every_seconds),
        (config.retention, retention_op, [clean_batch], config.retention_every_seconds),
        (config.capacity, capacity_op, [check_capacity], config.check_every_seconds),
        (config.notifications, notify_op, [send_notification], config.check_every_seconds),
    ]
    enabled = [(op, parts, seconds) for active, op, parts, seconds in definitions if active]

    # 存储注入只暴露框架允许的db参数。
    def factory(db: Db) -> Store:
        return Store(db, settings, verify, channel or Webhook(config))

    return Module(
        name="system_ops",
        title="框架内置运维",
        version="1",
        store=factory,
        tables=(state,),
        provides={
            op: Flow(op.title, work=Work, result="result", steps=parts) for op, parts, _ in enabled
        },
        jobs=tuple(
            JobPlan(
                op,
                repeat_safe=True,
                segmented=op is retention_op,
                cursor=Cursor if op is retention_op else None,
                lease_seconds=120,
            )
            for op, _, _ in enabled
        ),
        schedules=tuple(
            Schedule(
                op.name,
                op.title,
                op,
                Input(),
                every=timedelta(seconds=seconds),
                missed="latest",
                org_ids=(),
            )
            for op, _, seconds in enabled
        ),
    )
