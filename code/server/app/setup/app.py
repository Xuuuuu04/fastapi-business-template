"""
创建 FastAPI 单体应用。
统一登记路由、错误和请求处理，创建过程不连接数据库。
"""

from functools import partial

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.checks.request import RequestLog
from app.api.errors.handlers import register
from app.api.health.routes import router as health
from app.api.routes.monitor.routes import router as monitor
from app.api.routes.notes.routes import router as notes
from app.setup.build import notes as build_notes
from app.setup.life import lifespan
from app.setup.modules import MODULES
from shared.config.settings import Settings
from shared.modules.registry import Registry
from shared.monitor.trace import Monitor


# 组装应用，供运行、测试和离线文档导出共同使用。
def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(
        title=settings.name,
        version="0.1.0",
        description="单体后端初版：笔记业务、运行检查与统一错误。",
        docs_url="/docs" if settings.docs else None,
        redoc_url="/redoc" if settings.docs else None,
        openapi_url="/openapi.json" if settings.docs else None,
        lifespan=lifespan,
        openapi_tags=[
            {"name": "笔记", "description": "公开读取；写入需要 X-API-Key。"},
            {"name": "运行状态", "description": "分别检查进程与数据库。"},
        ],
    )
    app.state.settings = settings
    app.state.monitor = Monitor(settings.trace_limit, settings.monitor)
    app.state.registry = Registry(MODULES, app.state.monitor)
    app.state.notes = partial(build_notes, settings.db_path, app.state.registry)
    register(app)
    app.add_middleware(RequestLog)
    if settings.cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["Content-Type", "X-API-Key"],
            expose_headers=["X-Request-ID"],
        )
    app.include_router(health)
    app.include_router(notes)
    app.include_router(monitor)
    return app
