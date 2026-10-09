"""
记录通过 Db 执行的业务 SQL 耗时、行数和调用位置，不保存语句、参数或数据。
每步骤最多保留 200 次调用的细节；超出后继续统计次数和总耗时，明确标记细节不完整。
"""

import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from types import FrameType
from typing import cast

from sqlalchemy import Executable, Table
from sqlalchemy.sql import ClauseElement, visitors

from shared.records.models import DatabaseCallRecord, StepRecord

MAX_DATABASE_CALLS = 200


# 从最近的业务调用帧取得存储函数和准确行号，不保留帧或业务局部变量。
def caller_location(record: StepRecord) -> tuple[str, str]:
    frame: FrameType | None = sys._getframe(1)
    try:
        while frame is not None:
            path = frame.f_code.co_filename.replace("\\", "/")
            if "/service/" in path:
                return "service/" + path.split("/service/", 1)[
                    1
                ] + f":{frame.f_lineno}", frame.f_code.co_name
            frame = frame.f_back
        return record.source, record.name
    finally:
        del frame


# 存储位置另加字段，保留旧步骤fallback的source/function字段行为。
def storage_location(record: StepRecord) -> tuple[str, str]:
    frame: FrameType | None = sys._getframe(1)
    try:
        while frame is not None:
            path = frame.f_code.co_filename.replace("\\", "/")
            for root in ("/service/", "/tests/framework/"):
                if root in path:
                    return root[1:] + path.split(root, 1)[
                        1
                    ] + f":{frame.f_lineno}", frame.f_code.co_qualname
            frame = frame.f_back
        return record.source, record.name
    finally:
        del frame


# 表名来自 SQLAlchemy 表声明，包括以 Table 声明的视图；原始 SQL 不猜表名。
def table_names(statement: Executable) -> list[str]:
    return sorted(
        {
            node.fullname
            for node in visitors.iterate(cast(ClauseElement, statement))
            if isinstance(node, Table)
        }
    )


# 包含权限检查、实际执行与结果读取；失败仍记录耗时，并原样抛出。
@contextmanager
def query_record(
    record: StepRecord | None, statement: Executable, method: str, target: str
) -> Iterator[DatabaseCallRecord | None]:
    if record is None:
        yield None
        return
    source, function = caller_location(record)
    call = DatabaseCallRecord(
        method,
        target,
        getattr(statement, "__visit_name__", "unknown"),
        table_names(statement),
        source,
        function,
    )
    call.storage_source, call.storage_function = storage_location(record)
    record.database_count += 1
    if len(record.database) < MAX_DATABASE_CALLS:
        record.database.append(call)
    else:
        record.database_complete = False
    started = time.perf_counter()
    try:
        yield call
        call.status = "ok"
    except BaseException as error:
        call.status, call.error_code = "failed", type(error).__name__
        raise
    finally:
        call.elapsed_ms = (time.perf_counter() - started) * 1000
        record.database_elapsed_ms += call.elapsed_ms
        accumulate(record, call)


# SQL明细截断后仍累计总量与存储函数；函数分组本身有界，超出明确标不完整。
def accumulate(record: StepRecord, call: DatabaseCallRecord) -> None:
    for key in ("rows", "bytes"):
        value = getattr(call, key)
        attr = "database_" + key
        if value is None:
            attr += "_unknown"
            value = 1
        setattr(record, attr, getattr(record, attr) + value)
    key = (
        (call.storage_source or call.source).rsplit(":", 1)[0]
        + " · "
        + (call.storage_function or call.function)
    )
    if (
        key not in record.database_functions
        and len(record.database_functions) >= MAX_DATABASE_CALLS
    ):
        record.database_functions_complete = False
        return
    counts = record.database_functions.setdefault(key, dict(queries=0, rows=0, bytes=0))
    counts["queries"] += 1
    counts["rows"] += call.rows or 0
    counts["bytes"] += call.bytes or 0
