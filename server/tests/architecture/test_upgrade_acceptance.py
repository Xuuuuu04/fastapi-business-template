"""
从真实第二代源码建立合成三包产品，再实际应用三方升级、适配增量迁移并验证双库旧行。
"""

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


# 旧源码从本模板真实历史取出，归档解包只允许普通文件，不依赖其他产品。
def old_template(root: Path) -> Path:
    archive = subprocess.check_output(["git", "archive", BASE_REVISION], cwd=PROJECT)
    base = root / "old-template"
    base.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        source.extractall(base, filter="data")
    return base


# 第二代自己的工具生成业务和迁移，升级前的全部原件由本测试记录。
def old_product(base: Path, target: Path, env: dict[str, str]) -> str:
    run(
        base,
        [
            "../.agents/skills/fastapi-template/scripts/run_template.py",
            "start_project",
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
                "../.agents/skills/fastapi-module/scripts/run_module.py",
                "new_module",
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


# 必须人工适配的依赖、产品声明和框架新增迁移明确处理，已有迁移一个字节也不重写。
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
        '"""\n合成旧产品升级后的显式组装入口。\n"""\n\n'
        "from shared.application.spec import ApplicationSpec\n\n"
        'APPLICATION = ApplicationSpec(name="合成旧产品")\n'
    )
    for path in (PROJECT / "server/migrations/versions").glob("*.py"):
        destination = target / "server/migrations/versions" / path.name
        if not destination.exists():
            shutil.copy2(path, destination)
    # 两张意图表及资源表/任务新增列已人工核对，和三张sample业务表没有对象交集。
    run(
        target,
        ["-m", "alembic", "merge", "heads", "-m", "reviewed framework and business heads"],
        env,
    )
    merged = list(
        (target / "server/migrations/versions").glob("*reviewed_framework_and_business_heads.py")
    )
    for path in merged:
        text = path.read_text().replace(
            "def upgrade()", "# 合并只连接已人工审查的独立头。\ndef upgrade()"
        )
        text = text.replace("def downgrade()", "# 回退交还原有迁移头。\ndef downgrade()")
        path.write_text(text)
    run(target, ["-m", "ruff", "check", *[str(path) for path in merged], "--fix"], env)
    run(target, ["-m", "ruff", "format", *[str(path) for path in merged]], env)
    run(target, [*ENTRY, "framework-lock", "--update"], env)
    run(target, [*ENTRY, "docs"], env)


# 旧产品的业务、接口、手写文档、配置和迁移保护范围按真实文件生成。
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


# 双库的当前业务样例明确运行，不能用迁移成功代替业务检查。
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


# 真正应用框架更新后，旧行跨增量保留、全新结构相等，三个真实包的双库样例通过。
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
