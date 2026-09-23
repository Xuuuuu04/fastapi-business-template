"""
订单报价的步骤需要的数据访问操作。数据库实现见 sql.py。
"""

from datetime import datetime
from decimal import Decimal
from typing import Protocol

from service.order_quote.data import MemberLevel, QuoteLine, QuoteView


class QuoteStore(Protocol):
    # 保存一份报价及其明细，返回报价编号和保存时间。
    async def add(
        self,
        customer: str,
        member_level: MemberLevel,
        lines: list[QuoteLine],
        excluded: list[str],
        amounts: tuple[Decimal, Decimal, Decimal],
        explanation: str,
    ) -> tuple[int, datetime]: ...

    # 按编号读取报价，不存在时返回 None。
    async def find(self, quote_id: int) -> QuoteView | None: ...

    # 把创建时间早于 before 的有效报价标为过期，返回处理数量。
    async def expire(self, before: datetime) -> int: ...
