"""
真实生成项目的两包两迁移整合验收，不在正式空模板或任何产品数据库上开发业务。
"""

import json
import os
import subprocess
from pathlib import Path

import pytest
from fastapi_check.quality.rules import PROJECT

from tests.architecture.test_integration_git import run as git
from tests.architecture.test_operation_generators import COPY_FLAG, run
from tests.environment import subprocess_environment
from tests.template_project import initialize

ENTRY = ["-c", "from fastapi_dev.main import main; main()"]
MERGE = """
import json, os, sys
from pathlib import Path
from fastapi_dev.main import bootstrap
bootstrap(Path.cwd().parent)
from fastapi_project.development.integration_git import integrate
from fastapi_project.development.integration_resolve import resolve
from fastapi_project.integration import validation, refresh
root = Path.cwd().parent
validator = lambda tree: validation(root, tree, os.environ['APP_TEST_CONTROL_URL'], workers=4)
report = integrate(root, sys.argv[1], validator, resolve)
refresh(root, report)
print(json.dumps(report, ensure_ascii=False))
raise SystemExit(1 if report.get('error') or report.get('panel_error') else 0)
"""


# 每个分支从同一框架旧版生成自己的增量，DB文件在忽略目录且只用于本例。
def branch(copy: Path, name: str, env: dict[str, str]) -> None:
    run(copy, [*ENTRY, "new-module", name, "--title", "合成独立业务包"], env)
    database = copy / ".agents/records" / (name + ".db")
    database.parent.mkdir(parents=True, exist_ok=True)
    local = env | {"APP_ENV": "test", "APP_DATABASE_URL": "sqlite+aiosqlite:///" + str(database)}
    run(copy, ["-m", "alembic", "-x", "url=" + local["APP_DATABASE_URL"], "upgrade", "head"], local)
    run(
        copy,
        [
            "-m",
            "alembic",
            "-x",
            "url=" + local["APP_DATABASE_URL"],
            "revision",
            "--autogenerate",
            "-m",
            "synthetic " + name,
        ],
        local,
    )
    run(copy, ["-m", "ruff", "format", "migrations/versions"], local)
    run(copy, [*ENTRY, "docs"], env)
    git(copy, "add", ".")
    git(copy, "commit", "-m", "synthetic package and migration")


# 两个真包与接口/迁移冲突整合，完整双库证据必须导出并在原项目重读。
@pytest.mark.anyio
@pytest.mark.postgres_only
async def test_real_two_package_merge_and_dual_database_evidence(tmp_path: Path) -> None:
    if os.environ.get(COPY_FLAG):
        pytest.skip("生成副本不递归运行整合工具验收")
    control = os.environ.get("APP_TEST_CONTROL_URL")
    if not control:
        pytest.skip("需要显式PostgreSQL隔离测试控制连接")
    copy = tmp_path / "product"
    initialize(PROJECT, copy, "整合命令验收")
    env = subprocess_environment() | {COPY_FLAG: "1", "APP_TEST_CONTROL_URL": control}
    git(copy, "init", "-b", "main")
    git(copy, "config", "user.name", "synthetic-test")
    git(copy, "config", "user.email", "test@example.invalid")
    git(copy, "add", ".")
    git(copy, "commit", "-m", "synthetic baseline")
    base = git(copy, "rev-parse", "HEAD")
    branch(copy, "sample_left", env)
    git(copy, "switch", "-c", "incoming", base)
    branch(copy, "sample_right", env)
    git(copy, "switch", "main")
    result = subprocess.run(
        [os.sys.executable, "-c", MERGE, "incoming"],
        cwd=copy / "server",
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
    )
    report = json.loads(result.stdout.splitlines()[-1])
    try:
        assert result.returncode == 0, report
        assert report["applied"] and report["stage"] == "complete"
        assert report["evidence"]["migration"]["sqlite"]["schema_equal"]
        assert report["evidence"]["migration"]["postgresql"]["schema_equal"]
        assert (copy / report["panel"]).is_file()
        assert not git(copy, "status", "--porcelain")
        assert "sample_left" in (copy / "server/app/setup/catalog.py").read_text()
        assert "sample_right" in (copy / "server/app/api/routers.py").read_text()
    finally:
        tree = Path(report["tree"])
        if tree.is_dir():
            git(copy, "worktree", "remove", "--force", str(tree))
