"""
只计返回值的内容大小，不复制结果；不能代表数据库网络字节或Python对象内存。
"""

from collections.abc import Mapping, Sequence
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import RowMapping


# 文本按UTF-8，二进制按长度，普通标量按文字大小；其他类型保持未知。
def value_bytes(value: Any, depth: int = 0) -> int | None:
    if depth > 32:
        return None
    if value is None:
        return 0
    if isinstance(value, (bytes, bytearray, memoryview)):
        return len(value)
    if isinstance(value, str):
        if value.isascii():
            return len(value)
        return sum(
            1 if ord(char) < 128 else 2 if ord(char) < 2048 else 3 if ord(char) < 65536 else 4
            for char in value
        )
    if isinstance(value, (bool, int, float, Decimal, date, datetime, time, UUID)):
        return len(str(value).encode("utf-8"))
    if isinstance(value, Mapping):
        return container_bytes((part for pair in value.items() for part in pair), depth)
    if isinstance(value, (list, tuple)):
        return container_bytes(value, depth)
    return None


# 不序列化JSON列，逐项计内容；过深/循环对象明确未知。
def container_bytes(values: Any, depth: int) -> int | None:
    total = 0
    for value in values:
        size = value_bytes(value, depth + 1)
        if size is None:
            return None
        total += size
    return total


# 只计已返回行，不序列化业务正文；遇到不支持的列类型整次大小未知。
def rows_bytes(rows: Sequence[RowMapping]) -> int | None:
    total = 0
    for row in rows:
        for value in row.values():
            size = value_bytes(value)
            if size is None:
                return None
            total += size
    return total
