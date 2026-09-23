"""
测试专用的接口：把示例计算模块接到 HTTP 上，供系统接口和安全测试使用，
使这些框架测试不依赖可删除的示例业务。
"""

from fastapi import APIRouter

from app.api.runner import RunDep
from tests.framework.sample_modules import CalcInput, CalcResult, calc

sample_router = APIRouter(prefix="/test", tags=["测试"])


# 执行示例计算。
@sample_router.post("/calc", operation_id="test_calc", summary="示例计算")
async def run_calc(body: CalcInput, run: RunDep) -> CalcResult:
    return await run(calc, body)
