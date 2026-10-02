"""
定义在 SQLite 和 PostgreSQL 上行为一致的列类型。
UtcTime 保存带时区的时间，读出时一律是 UTC；ExactNumber 保存精确小数，读出时是 Decimal。
SQLite 没有这两种原生类型，所以在 SQLite 上按文本保存；时间固定写到微秒，保证按文本比较时顺序正确。
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Dialect, Numeric, String
from sqlalchemy.types import TypeDecorator, TypeEngine


# 数据库时间字段的类型，统一按 UTC 保存与读取。
class UtcTime(TypeDecorator[datetime]):
    impl = DateTime(timezone=True)
    cache_ok = True

    # SQLite 用文本保存时间，PostgreSQL 用带时区的时间类型。
    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(40))
        return dialect.type_descriptor(DateTime(timezone=True))

    # 写入前检查时间带时区，并统一转成 UTC。
    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> Any:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("保存的时间必须带时区，例如 datetime.now(UTC)")
        moment = value.astimezone(UTC)
        return moment.isoformat(timespec="microseconds") if dialect.name == "sqlite" else moment

    # 读出后统一返回 UTC 时间。
    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        moment = datetime.fromisoformat(value) if isinstance(value, str) else value
        return moment.astimezone(UTC)


# 数据库中的精确数值类型，避免金额因浮点计算出现误差。
class ExactNumber(TypeDecorator[Decimal]):
    impl = Numeric
    cache_ok = True

    # 设置总位数和小数位数，例如金额用 ExactNumber(14, 2)；参数名与 Numeric 相同，迁移文件才完整。
    def __init__(self, precision: int = 18, scale: int = 2) -> None:
        super().__init__(precision=precision, scale=scale)
        self.precision = precision
        self.scale = scale

    # SQLite 用文本保存以免丢失精度，PostgreSQL 用 NUMERIC。
    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(self.precision + 2))
        return dialect.type_descriptor(Numeric(self.precision, self.scale))

    # 写入前确认是 Decimal，避免浮点数带来的误差。
    def process_bind_param(self, value: Decimal | None, dialect: Dialect) -> Any:
        if value is None:
            return None
        if not isinstance(value, Decimal):
            raise ValueError("精确小数列只接受 Decimal，不接受浮点数")
        return str(value) if dialect.name == "sqlite" else value

    # 读出后统一返回 Decimal。
    def process_result_value(self, value: Any, dialect: Dialect) -> Decimal | None:
        return None if value is None else Decimal(str(value))
