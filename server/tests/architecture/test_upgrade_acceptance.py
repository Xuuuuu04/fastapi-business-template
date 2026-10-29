import io
import json
import os
import shutil
import subprocess
import tarfile
import tomllib
from pathlib import Path

import pytest
from fastapi_check.quality.rules import PROJECT
from fastapi_project.development.migration_graph import read_graph
from fastapi_project.development.migration_verify import verify
from fastapi_template.template.merge import apply_plan, update_plan

from tests.architecture.test_operation_generators import COPY_FLAG, run
from tests.environment import subprocess_environment

BASE_REVISION = "917a914"
PACKAGES = ("sample_orders", "sample_items", "sample_customers")
ENTRY = ["-c", "from fastapi_dev.main import main; main()"]


def old_template(root: Path) -> Path:
    archive = subprocess.check_output(["git", "archive", BASE_REVISION], cwd=PROJECT)
    base = root / "old-template"
    base.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        source.extractall(base, filter="data")
    return base


def old_product(base: Path, target: Path, env: dict[str, str]) -> str:
    run(
        base,
        [
            "-m",
            "fastapi_dev.main",
            "new-project",
            str(target),
            "--name",
            "合成旧产品",
        ],
        env,
    )
    for name in PACKAGES:
        run(
            target,
            [
                "-m",
                "fastapi_dev.main",
                "new-module",
                name,
                "--title",
                "合成历史业务",
            ],
            env,
        )
    run(target, ["-m", "alembic", "upgrade", "head"], env)
    run(
        target, ["-m", "alembic", "revision", "--autogenerate", "-m", "synthetic old business"], env
    )
    generated = list((target / "server/migrations/versions").glob("*synthetic_old_business.py"))
    run(target, ["-m", "ruff", "format", *[str(path) for path in generated]], env)
    run(target, ["-m", "alembic", "upgrade", "head"], env)
    metadata = target / "server/pyproject.toml"
    metadata.write_text(
        metadata.read_text().replace("dependencies = [", 'dependencies = [\n  "anyio>=4,<5",', 1)
    )
    (target / "server/.env.example").write_text(
        (target / "server/.env.example").read_text() + "\n# 合成产品自己的配置说明\n"
    )
    output = run(target, ["-m", "alembic", "current"], env)
    return output.strip().split()[0]


def adapt_product(target: Path, env: dict[str, str]) -> None:
    metadata = (PROJECT / "server/pyproject.toml").read_text()
    version = tomllib.loads(metadata)["project"]["version"]
    metadata = metadata.replace('name = "fastapi-server-template"', 'name = "product-server"')
    metadata = metadata.replace(f'version = "{version}"', 'version = "0.1.0"', 1)
    metadata = metadata.replace("dependencies = [", 'dependencies = [\n  "anyio>=4,<5",', 1)
    (target / "server/pyproject.toml").write_text(metadata)
    shutil.copy2(PROJECT / "server/uv.lock", target / "server/uv.lock")
    run(
        target,
        ["-c", "import subprocess; subprocess.run(['uv','lock','--offline'],check=True)"],
        env,
    )
    (target / "server/app/product.py").write_text(
        "from shared.application.spec import ApplicationSpec\n\n"
        'APPLICATION = ApplicationSpec(name="合成旧产品")\n'
    )
    for path in (PROJECT / "server/migrations/versions").glob("*.py"):
        destination = target / "server/migrations/versions" / path.name
        if not destination.exists():
            shutil.copy2(path, destination)
    run(
        target,
        ["-m", "alembic", "merge", "heads", "-m", "reviewed framework and business heads"],
        env,
    )
    merged = list(
        (target / "server/migrations/versions").glob("*reviewed_framework_and_business_heads.py")
    )
    run(target, ["-m", "ruff", "check", *[str(path) for path in merged], "--fix"], env)
    run(target, ["-m", "ruff", "format", *[str(path) for path in merged]], env)
    run(target, [*ENTRY, "framework-lock", "--update"], env)
    run(target, [*ENTRY, "docs"], env)


def protected(target: Path) -> dict[Path, bytes]:
    paths = []
    for name in ("server/service", "server/app/api/v1", "server/migrations/versions", "doc"):
        paths += [
            path
            for path in (target / name).rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        ]
    paths += [target / "server/.env.example", target / "server/pyproject.toml"]
    return {path: path.read_bytes() for path in paths}


def check_product(target: Path, control: str, env: dict[str, str]) -> None:
    arguments = [*ENTRY, "check", "--database", "both", "--postgres", control, "--workers", "0"]
    for name in PACKAGES:
        arguments += ["--module", name]
    output = run(target, arguments, env)
    checks = list((target / "server/var/development/checks").glob("*.json"))
    assert checks, output[-1000:]
    result = json.loads(checks[-1].read_text())
    assert result["passed"] and not result["source_changed"]
    assert "anyio>=4,<5" in (target / "server/pyproject.toml").read_text()
    assert "合成产品自己的配置说明" in (target / "server/.env.example").read_text()


@pytest.mark.anyio
@pytest.mark.postgres_only
async def test_real_v2_product_upgrade_and_incremental_databases(tmp_path: Path) -> None:
    if os.environ.get(COPY_FLAG):
        pytest.skip("产品副本不递归执行真实历史升级验收")
    control = os.environ.get("APP_TEST_CONTROL_URL")
    if not control:
        pytest.skip("需要显式隔离PostgreSQL控制连接")
    base = old_template(tmp_path)
    target = tmp_path / "product"
    env = subprocess_environment() | {
        COPY_FLAG: "1",
        "APP_ENV": "test",
        "APP_DATABASE_URL": "sqlite+aiosqlite:///" + str(tmp_path / "old.db"),
    }
    anchor = old_product(base, target, env)
    originals = protected(target)
    changes, manual = update_plan(target, base, PROJECT)
    assert changes and not any(change.state == "conflict" for change in changes)
    assert "server/pyproject.toml" in manual
    apply_plan(target, base, PROJECT, changes)
    assert all(path.read_bytes() == content for path, content in originals.items())
    adapt_product(target, env)
    graph = read_graph(target)
    parents = {parent for node in graph.values() for parent in node.parents}
    assert anchor in graph and len(set(graph) - parents) == 1
    evidence = await verify(
        target,
        anchor,
        control,
        [
            {
                "table": "sample_orders_records",
                "values": {
                    "id": 7,
                    "title": "合成旧行",
                    "created_at": "2026-10-13T00:00:00.000000+00:00",
                },
            }
        ],
    )
    assert all(
        evidence[database]["schema_equal"] and evidence[database]["seed_rows_preserved"]
        for database in ("sqlite", "postgresql")
    )
    check_product(target, control, env)
