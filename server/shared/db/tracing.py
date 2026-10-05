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
