"""
订单报价的数据库实现，SQL 都集中在这里。不负责提交或回滚。
"""

import json
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import ColumnElement, insert, select, update

from service.order_quote.data import MemberLevel, QuoteLine, QuoteView
from service.order_quote.store.tables import quote_lines, quotes
from shared.public import Caller, Db


class SqlQuoteStore:
    # 使用框架提供的数据库入口和调用者身份。
    def __init__(self, db: Db, caller: Caller) -> None:
        self.db = db
        self.caller = caller

    # 按 R-07 限定只看自己创建的报价；有 order_quote.manage 权限时看全部。
    def mine(self) -> list[ColumnElement[bool]]:
        if self.caller.can("order_quote.manage"):
            return []
        return [quotes.c.owner_id == self.caller.id]

    # 保存报价主表和明细。
    async def add(
        self,
        customer: str,
        member_level: MemberLevel,
        lines: list[QuoteLine],
        excluded: list[str],
        amounts: tuple[Decimal, Decimal, Decimal],
        explanation: str,
    ) -> tuple[int, datetime]:
        subtotal, discount, total = amounts
        created_at = datetime.now(UTC)
        values = {"customer": customer, "member_level": member_level, "subtotal": subtotal}
        values |= {"discount": discount, "total": total, "excluded": json.dumps(excluded)}
        values |= {"explanation": explanation, "status": "active", "created_at": created_at}
        values |= {"owner_id": self.caller.id}
        row = await self.db.one(insert(quotes).values(**values).returning(quotes.c.id))
        rows = [{"quote_id": row["id"], **line.model_dump()} for line in lines]
        await self.db.change(insert(quote_lines).values(rows))
        return row["id"], created_at

    # 读取报价和明细。
    async def find(self, quote_id: int) -> QuoteView | None:
        head = await self.db.first(select(quotes).where(quotes.c.id == quote_id, *self.mine()))
        if head is None:
            return None
        query = (
            select(quote_lines).where(quote_lines.c.quote_id == quote_id).order_by(quote_lines.c.id)
        )
        lines = [
            QuoteLine(
                code=row["code"],
                quantity=row["quantity"],
                unit_price=row["unit_price"],
                amount=row["amount"],
            )
            for row in await self.db.all(query)
        ]
        return QuoteView(
            id=head["id"],
            customer=head["customer"],
            member_level=head["member_level"],
            lines=lines,
            excluded=json.loads(head["excluded"]),
            subtotal=head["subtotal"],
            discount=head["discount"],
            total=head["total"],
            explanation=head["explanation"],
            status=head["status"],
            created_at=head["created_at"],
        )

    # 把早于 before 的有效报价标为过期。
    async def expire(self, before: datetime) -> int:
        statement = (
            update(quotes)
            .where(quotes.c.status == "active", quotes.c.created_at < before)
            .values(status="expired")
        )
        return await self.db.change(statement)
