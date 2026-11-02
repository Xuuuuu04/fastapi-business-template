import inspect
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.setup.build import Services
from shared.application.spec import ApplicationSpec
from shared.config.settings import Settings
from shared.db.schema import head_revision
from shared.db.tables import metadata


def isolated_settings(specification: ApplicationSpec, folder: Path) -> Settings:
    if specification.providers or specification.adapters or specification.model_provider:
        raise ValueError("验收服务暂不支持自定义外部供应商、适配器或模型工厂")
    settings = specification.settings(
        "test",
        database_url=f"sqlite+aiosqlite:///{folder}/acceptance.db",
        file_root=str(folder / "files"),
        upload_root=str(folder / "uploads"),
        code_version="acceptance",
        docs=True,
        run_records="memory",
    )
    check_isolation(settings, folder)
    return settings


def check_isolation(settings: Settings, folder: Path) -> None:
    expected = {
        "env": "test",
        "database_url": f"sqlite+aiosqlite:///{folder}/acceptance.db",
        "file_root": str(folder / "files"),
        "upload_root": str(folder / "uploads"),
        "file_storage": "local",
        "run_records": "memory",
        "database_org_setting": "",
        "job_health_file": "",
    }
    changed = [name for name, value in expected.items() if getattr(settings, name) != value]
    outside = [
        name
        for name in (
            "cache_url",
            "legacy_database_url",
            "model_base_url",
            "model_api_key",
            "model_name",
            "remotes",
            "s3_bucket",
            "s3_endpoint",
            "s3_access_key",
            "s3_secret_key",
            "otel_endpoint",
        )
        if getattr(settings, name)
    ]
    if changed or outside:
        raise ValueError("验收配置不满足隔离要求：" + "、".join(changed + outside))


async def create_schema(services: Services) -> None:
    async with services.database.write() as connection:
        await connection.run_sync(metadata.create_all)
        await connection.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        )
        await connection.execute(
            text("INSERT INTO alembic_version VALUES (:head)"), {"head": head_revision()}
        )


async def prepare_seed(services: Services, folder: Path, project: Path) -> None:
    path = project / "server/tests/acceptance/seed.py"
    if not path.is_file() or path.is_symlink():
        raise ValueError("--seed 需要产品提供 server/tests/acceptance/seed.py 普通文件")
    module_spec = spec_from_file_location("product_acceptance_seed", path)
    if module_spec is None or module_spec.loader is None:
        raise ValueError("无法加载产品验收准备函数")
    module = module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    prepare: Any = getattr(module, "prepare", None)
    if not inspect.iscoroutinefunction(prepare):
        raise ValueError("验收准备函数必须是 async prepare(services, folder)")
    await prepare(services, folder)
    check_isolation(services.settings, folder)
