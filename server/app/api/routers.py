"""
系统接口和业务接口的清单。业务接口随对应模块启用；新模块由 uv run dev new-module 登记。
"""

from collections.abc import Collection

from fastapi import APIRouter

from app.api.system import audit, console, health, jobs, pipelines, runs, structure
from app.api.v1 import stream

ROUTERS: list[APIRouter] = [
    health.router,
    structure.router,
    runs.router,
    jobs.router,
    pipelines.router,
    audit.router,
    console.router,
    stream.router,
]

MODULE_ROUTERS: dict[str, tuple[APIRouter, ...]] = {}


# 系统接口始终可用，业务接口随模块一起启用或关闭。
def routers_for(modules: Collection[str]) -> list[APIRouter]:
    business = [
        router for name, routers in MODULE_ROUTERS.items() if name in modules for router in routers
    ]
    return [*ROUTERS, *business]
