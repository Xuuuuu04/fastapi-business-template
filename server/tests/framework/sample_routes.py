from fastapi import APIRouter

from app.api.runner import RunDep
from tests.framework.sample_modules import CalcInput, CalcResult, calc

sample_router = APIRouter(prefix="/test", tags=["测试"])


@sample_router.post("/calc", operation_id="test_calc", summary="示例计算")
async def run_calc(body: CalcInput, run: RunDep) -> CalcResult:
    return await run(calc, body)
