from typing import Any

from sqlalchemy import Executable, Select, text
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.records.models import DatabaseCallRecord, StepRecord

SAFE_KEYS = ("Node Type", "Relation Name", "Plan Rows", "Plan Width", "Total Cost")


async def attach(
    connection: AsyncConnection,
    record: StepRecord | None,
    statement: Executable,
    call: DatabaseCallRecord | None,
) -> None:
    if (
        record is None
        or call is None
        or not record.database_explain
        or connection.dialect.name != "postgresql"
        or not isinstance(statement, Select)
        or getattr(statement, "_for_update_arg", None) is not None
    ):
        return
    limits, prior = record.query_limits, record.query_prior
    key = (
        (call.storage_source or call.source).rsplit(":", 1)[0]
        + " · "
        + (call.storage_function or call.function)
    )
    repeated = record.database_functions.get(key, {}).get("queries", 0) + 1
    if not (
        prior.get("queries", 0) + record.database_count > limits["queries"]
        or repeated > limits["repeated"]
        or prior.get("rows", 0) + record.database_rows + (call.rows or 0) > limits["rows"]
        or prior.get("bytes", 0) + record.database_bytes + (call.bytes or 0) > limits["bytes"]
    ):
        return
    if sum(bool(item.explain_status) for item in record.database) >= 3:
        return
    try:
        compiled = statement.compile(compile_kwargs={"render_postcompile": True})
        async with connection.begin_nested():
            result = await connection.scalar(
                text("EXPLAIN (FORMAT JSON) " + str(compiled)), compiled.params
            )
        call.explain = plan_summary(result)
        call.explain_status = "ok"
    except Exception:
        call.explain_status = "未知"


def plan_summary(result: Any) -> list[dict[str, Any]]:
    if not isinstance(result, list) or not result:
        return []
    pending = [result[0].get("Plan", {})]
    output: list[dict[str, Any]] = []
    while pending and len(output) < 20:
        node = pending.pop(0)
        output.append({key: node[key] for key in SAFE_KEYS if key in node})
        pending.extend(node.get("Plans", [])[:20])
    return output
