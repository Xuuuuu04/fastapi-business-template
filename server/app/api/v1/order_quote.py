"""
订单报价的 HTTP 接口（第 1 版）。创建和读取直接返回结果；标记过期作为后台任务受理，返回任务编号。
"""

from typing import Annotated

from fastapi import APIRouter, Header, Path

from app.api.replies import JobAccepted, responses_for
from app.api.runner import RunDep
from service.order_quote import public as quotes

router = APIRouter(prefix="/api/v1/quotes", tags=["订单报价"])


# 按明细计算报价、生成说明并保存。
@router.post(
    "",
    status_code=201,
    summary="创建报价",
    operation_id="create_quote",
    response_model=quotes.QuoteView,
    responses=responses_for(quotes.create_quote),
)
async def create_quote(body: quotes.QuoteRequest, run: RunDep) -> quotes.QuoteView:
    return await run(quotes.create_quote, body)


# 按编号读取报价。
@router.get(
    "/{quote_id}",
    summary="读取报价",
    operation_id="get_quote",
    response_model=quotes.QuoteView,
    responses=responses_for(quotes.get_quote),
)
async def get_quote(
    quote_id: Annotated[int, Path(gt=0, description="报价编号")], run: RunDep
) -> quotes.QuoteView:
    return await run(quotes.get_quote, quotes.QuoteId(quote_id=quote_id))


# 受理“标记过期报价”后台任务；同一个 Idempotency-Key 重复提交返回原任务。
@router.post(
    "/expire",
    status_code=202,
    summary="标记过期报价（后台任务）",
    operation_id="expire_quotes",
    response_model=JobAccepted,
    responses=responses_for(quotes.expire_quotes),
)
async def expire_quotes(
    body: quotes.ExpireRequest,
    run: RunDep,
    idempotency_key: Annotated[
        str, Header(max_length=120, description="请求编号，重复提交时用来识别同一个请求")
    ] = "",
) -> JobAccepted:
    return await run.later(quotes.expire_quotes, body, key=idempotency_key)
