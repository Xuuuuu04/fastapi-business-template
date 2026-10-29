import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi_check.quality.rules import PROJECT

from tests.environment import subprocess_environment
from tests.template_project import initialize

COPY_FLAG = "TEMPLATE_COPY_RUN"


def run(copy: Path, arguments: list[str], env: dict[str, str]) -> str:
    result = subprocess.run(
        [sys.executable, *arguments],
        cwd=copy / "server",
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout[-2500:] + result.stderr[-2500:]
    return result.stdout


def snapshot(copy: Path) -> dict[str, bytes]:
    excluded = {"var", "__pycache__", ".mypy_cache", ".ruff_cache", ".venv"}
    summaries = {"doc/development.md", "doc/modules.md", "doc/progress.md"}
    return {
        str(path.relative_to(copy)): path.read_bytes()
        for path in copy.rglob("*")
        if path.is_file()
        and not excluded.intersection(path.relative_to(copy).parts)
        and str(path.relative_to(copy)) not in summaries
    }


@pytest.mark.sqlite_template
def test_new_operation_and_pipeline_check_without_manual_edits(tmp_path: Path) -> None:
    if os.environ.get(COPY_FLAG):
        pytest.skip("模板副本不再次复制生成器验收")
    copy = tmp_path / "product"
    initialize(PROJECT, copy, "生成器独立样例")
    env = subprocess_environment()
    env |= {COPY_FLAG: "1", "APP_DATABASE_URL": f"sqlite+aiosqlite:///{tmp_path}/baseline.db"}
    dev = ["-m", "fastapi_dev.main"]
    run(copy, [*dev, "new-module", "sample_operations", "--title", "独立样例"], env)
    run(copy, ["-m", "alembic", "upgrade", "head"], env)
    run(
        copy, ["-m", "alembic", "revision", "--autogenerate", "-m", "existing module baseline"], env
    )
    run(copy, ["-m", "ruff", "format", "migrations"], env)
    before = snapshot(copy)
    run(
        copy,
        [
            *dev,
            "new-operation",
            "sample_operations",
            "normalize_text",
            "--title",
            "整理文本",
            "--preview",
        ],
        env,
    )
    assert snapshot(copy) == before
    result = run(
        copy,
        [
            *dev,
            "new-operation",
            "sample_operations",
            "normalize_text",
            "--title",
            "整理文本",
            "--http",
        ],
        env,
    )
    reported = set(json.loads(result)["files"])
    after = snapshot(copy)
    changed = {name for name, value in after.items() if before.get(name) != value}
    assert reported == changed
    run(copy, [*dev, "new-pipeline", "sample_operations", "daily", "--title", "阶段样例"], env)
    result = run(copy, [*dev, "check", "--module", "sample_operations", "--workers", "0"], env)
    assert "通过  模块测试" in result and "失败  " not in result
