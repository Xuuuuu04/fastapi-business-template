"""
管理单体应用的运行生命周期。
启动时设置日志，不自动迁移数据库或启动后台任务。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.logs.config import configure


# 在应用启动时准备运行日志。
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure()
    yield
