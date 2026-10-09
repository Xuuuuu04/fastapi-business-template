"""
内置运维挂载与恢复启动校验，组装层可以依赖HTTP启动而公共框架不反向依赖。
"""

import shutil
from collections.abc import Sequence
from pathlib import Path

import httpx2

from shared.config.settings import Settings
from shared.errors.framework import ConfigError
from shared.modules.module import Module
from shared.operations.config import OperationsConfig
from shared.operations.module import make_module


# 只有开启的功能才登记；备份目录不得位于源文件/上传区，否则可能递归备份和误清理。
def with_operations(settings: Settings, modules: Sequence[Module]) -> list[Module]:
    if not settings.operations.enabled():
        return list(modules)
    problems = []
    root = Path(settings.operations.backup_root).resolve()
    if settings.operations.backup:
        if any(
            root.is_relative_to(Path(path).resolve())
            for path in (settings.file_root, settings.upload_root)
        ):
            problems.append("备份目录不能位于正式文件或上传目录内")
        if settings.database_url.startswith("postgresql") and not all(
            shutil.which(tool) for tool in ("pg_dump", "pg_restore")
        ):
            problems.append("PostgreSQL内置备份需要pg_dump和pg_restore")
    if problems:
        raise ConfigError(problems)

    # 用原产品声明启动恢复服务，不启用运维或后台入口。
    async def verify(url: str, files: Path) -> None:
        await restored_ready(settings, modules, url, files)

    return [*modules, make_module(settings, verify)]


# 恢复只连接随机库与恢复文件，不跑worker或访问真实外部系统；实际应用ready检查迁移版本。
async def restored_ready(
    settings: Settings, modules: Sequence[Module], url: str, files: Path
) -> None:
    from app.setup.build import build
    from app.setup.web import create_app
    from shared.model_calls.providers import FakeModel

    config = settings.model_copy(
        update=dict(
            env="test",
            database_url=url,
            operations=OperationsConfig(),
            file_storage="local",
            file_root=str(files),
            cache_url="",
            run_records="memory",
        )
    )
    services = build(config, modules=modules, provider=FakeModel())
    try:
        app = create_app(config, services=services)
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://restore"
        ) as client:
            response = await client.get("/health/ready")
        if response.status_code != 200 or response.json()["status"] != "ready":
            raise ValueError("恢复应用未ready或迁移版本不符")
    finally:
        await services.close()
