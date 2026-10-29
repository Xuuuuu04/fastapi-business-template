from fastapi import APIRouter

from app.api.runner import FailureLimit, RunDep
from tests.framework.sample_modules import CalcInput, CalcResult, SampleBusy, calc

sample_router = APIRouter(prefix="/test", tags=["测试"])
BUSY_LIMIT = FailureLimit("sample-busy", ("vip",), limit=2, seconds=60, errors=(SampleBusy,))


@sample_router.post("/calc", operation_id="test_calc", summary="示例计算")
async def run_calc(body: CalcInput, run: RunDep) -> CalcResult:
    return await run(calc, body)


@sample_router.post(
    "/limited-calc", operation_id="test_limited_calc", summary="限制失败次数的示例计算"
)
async def run_limited_calc(body: CalcInput, run: RunDep) -> CalcResult:
    return await run(calc, body, limits=(BUSY_LIMIT,))
