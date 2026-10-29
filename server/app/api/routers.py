from collections.abc import Collection

from fastapi import APIRouter

from app.api.system import audit, console, health, jobs, pipelines, runs, stream, structure

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


def routers_for(modules: Collection[str]) -> list[APIRouter]:
    business = [
        router for name, routers in MODULE_ROUTERS.items() if name in modules for router in routers
    ]
    return [*ROUTERS, *business]
