"""
固定来源的数据导入声明与提交前对账，不把命令返回值当成导入证据。
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING, Any

from sqlalchemy import Column, Float, Integer, Numeric, Table, func, select
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.sql.elements import ColumnElement

from shared.db.types import ExactNumber
from shared.errors.framework import StepRuleBroken

if TYPE_CHECKING:
    from shared.jobs.checkpoint import Checkpoint
    from shared.jobs.plan import JobPlan
    from shared.jobs.queue import JobQueue, Ticket
    from shared.records.models import RunRecord


# 在读取任务输入和写入业务数据前确认仍使用登记时的固定来源。
async def check_import_source(queue: "JobQueue", ticket: "Ticket", plan: "JobPlan") -> bool:
    if plan.import_plan is None or ticket.key == plan.import_plan.queue_key():
        return True
    await queue.fail(
        ticket, "blocked", "import_source_changed", "导入来源或对账计划已变化，需要人工确认"
    )
    return False


# 一个导入字段必须引用目标表中实际存在的值，空值质量另行登记。
@dataclass(frozen=True)
class ImportReference:
    column: str
    target: Column[Any]


# 预期来自固定来源清单；where必须限定本次导入范围，不能拿全库总量凑数。
@dataclass(frozen=True)
class Reconcile:
    table: Table
    rows: int
    sums: Mapping[str, Decimal] = field(default_factory=dict)
    non_null: Mapping[str, float] = field(default_factory=dict)
    references: tuple[ImportReference, ...] = ()
    where: ColumnElement[bool] | None = None
    allow_empty: bool = False


# 在JobPlan中登记，复用分段提交；来源版本与范围键也用于任务去重。
@dataclass(frozen=True)
class ImportPlan:
    source_revision: str
    key: str
    reconcile: Reconcile

    # 声明摘要覆盖预期和范围，变更之后旧任务不能冒用新来源。
    def shape(self) -> dict[str, Any]:
        rule = self.reconcile
        return dict(
            source_revision=self.source_revision,
            key=self.key,
            table=rule.table.key,
            rows=rule.rows,
            sums={name: str(value) for name, value in rule.sums.items()},
            non_null=dict(rule.non_null),
            references=[(item.column, str(item.target)) for item in rule.references],
            where=str(rule.where.compile(compile_kwargs={"literal_binds": True}))
            if rule.where is not None
            else None,
            allow_empty=rule.allow_empty,
        )

    # 同一个来源范围和预期只登记一次，已有队列校验输入摘要是否一致。
    def queue_key(self) -> str:
        body = json.dumps(self.shape(), sort_keys=True, ensure_ascii=False)
        return "import:" + hashlib.sha256(body.encode()).hexdigest()


# 启动前确认完整预期和表归属，避免执行到最后才发现对账声明不能用。
def check_import(plan: ImportPlan, tables: tuple[Table, ...]) -> list[str]:
    rule = plan.reconcile
    problems = []
    if not plan.source_revision.strip() or not plan.key.strip():
        problems.append("导入必须登记非空 source_revision 和 key")
    if rule.table not in tables:
        problems.append(f"导入目标表 {rule.table.key} 必须登记在模块 tables")
    if type(rule.rows) is not int or rule.rows < 0 or (rule.rows == 0 and not rule.allow_empty):
        problems.append("导入预期行数必须为正整数；确认空来源才显式声明 allow_empty=True")
    for name in (*rule.sums, *rule.non_null, *(item.column for item in rule.references)):
        if name not in rule.table.c:
            problems.append(f"导入对账字段 {rule.table.key}.{name} 不存在")
    problems += check_sum_columns(rule)
    if any(not Decimal(str(value)).is_finite() for value in rule.sums.values()):
        problems.append("导入合计预期必须是有限的精确数值")
    if any(not 0 <= value <= 1 for value in rule.non_null.values()):
        problems.append("导入质量非空率必须在0到1之间")
    for item in rule.references:
        if item.target.table is None or item.target.table not in tables:
            problems.append("导入引用目标必须登记在同模块 tables")
    return problems


# 合计只接受数据库里的精确数值字段，避免浮点误差成为验收依据。
def check_sum_columns(rule: Reconcile) -> list[str]:
    problems = []
    for name in rule.sums:
        if name in rule.table.c:
            kind = rule.table.c[name].type
            if isinstance(kind, Float) or not isinstance(kind, (Integer, Numeric, ExactNumber)):
                problems.append(f"导入合计字段 {name} 必须是整数或精确小数，不能用浮点数")
    return problems


# 入口不能跳过分段执行，尚未执行的对账保留未知。
def begin_import(
    plan: ImportPlan | None, checkpoint: "Checkpoint | None", run: "RunRecord"
) -> None:
    if plan is None:
        return
    run.import_report = dict(source_revision=plan.source_revision, key=plan.key, status="未知")
    if checkpoint is None:
        raise StepRuleBroken("数据导入必须通过分段后台任务执行")


# 在最后一批的写入事务里读真实目标，不使用checkpoint或shell的返回行数。
async def reconcile_import(
    connection: AsyncConnection, plan: ImportPlan, report: dict[str, Any]
) -> None:
    rule, table = plan.reconcile, plan.reconcile.table
    report.update(source_revision=plan.source_revision, key=plan.key, status="未知", checks={})
    checks = report["checks"]

    # 每条指标记录预期与实测，不保存数据正文。
    def record(name: str, actual: Any, expected: Any, passed: bool) -> None:
        checks[name] = dict(actual=str(actual), expected=str(expected), passed=passed)

    # 所有指标共享固定范围，合计和质量由数据库聚合，不将数据装入内存。
    async def scalar(expression: Any) -> Any:
        query = select(expression).select_from(table)
        if rule.where is not None:
            query = query.where(rule.where)
        return (await connection.execute(query)).scalar_one()

    rows = int(await scalar(func.count()))
    record("rows", rows, rule.rows, rows == rule.rows)
    totals = await exact_totals(connection, rule)
    for name, expected in rule.sums.items():
        actual = totals[name]
        record(f"sum:{name}", actual, expected, actual == Decimal(str(expected)))
    for name, minimum in rule.non_null.items():
        present = int(await scalar(func.count(table.c[name])))
        rate = Decimal(present) / rows if rows else Decimal(0)
        record(f"non_null:{name}", rate, minimum, rate >= Decimal(str(minimum)))
    for item in rule.references:
        column = table.c[item.column]
        target = item.target.table.alias()
        target_column = target.c[item.target.name]
        exists = select(target_column).where(target_column == column).exists()
        query = select(func.count()).select_from(table).where(column.is_not(None), ~exists)
        if rule.where is not None:
            query = query.where(rule.where)
        missing = int((await connection.execute(query)).scalar_one())
        record(f"reference:{item.column}", missing, 0, missing == 0)
    failed = [name for name, value in checks.items() if not value["passed"]]
    report["status"] = "失败" if failed else "通过"
    if failed:
        raise StepRuleBroken("数据导入对账失败：" + "、".join(failed))


# SQLite的SUM会把文本小数转换成浮点数；有界流式读取保证两种数据库都精确相加。
async def exact_totals(connection: AsyncConnection, rule: Reconcile) -> dict[str, Decimal]:
    totals = {name: Decimal(0) for name in rule.sums}
    if not totals:
        return totals
    columns = [rule.table.c[name] for name in totals]
    query = select(*columns)
    if rule.where is not None:
        query = query.where(rule.where)
    with localcontext() as context:
        context.prec = max(
            [100, *((getattr(column.type, "precision", None) or 0) + 30 for column in columns)]
        )
        async with connection.stream(query.execution_options(yield_per=1000)) as result:
            async for row in result:
                for name, value in zip(totals, row, strict=True):
                    totals[name] += Decimal(str(value)) if value is not None else Decimal(0)
    return totals
