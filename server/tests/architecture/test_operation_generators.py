"""
独立模板副本验收生成器：预览无写入、文件报告准确、新操作和流程不手工补文件通过模块检查。
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi_check.quality.rules import PROJECT
from fastapi_template.template.initialization import initialize

COPY_FLAG = "TEMPLATE_COPY_RUN"


# 单个副本共用环境，所有步骤只使用隔离SQLite或显式测试PostgreSQL。
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


# 实际源文件快照排除运行缓存及不提交汇总，与生成器Git影响清单口径相同。
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


# 原模块的基线迁移建立一次，新增操作本身不需要手工补其他代码或环境。
@pytest.mark.sqlite_template
def test_new_operation_and_pipeline_check_without_manual_edits(tmp_path: Path) -> None:
    if os.environ.get(COPY_FLAG):
        pytest.skip("模板副本不再次复制生成器验收")
    copy = tmp_path / "product"
    initialize(PROJECT, copy, "生成器独立样例")
    env = {name: value for name, value in os.environ.items() if not name.startswith("APP_")}
    env |= {COPY_FLAG: "1", "APP_DATABASE_URL": f"sqlite+aiosqlite:///{tmp_path}/baseline.db"}
    runner = "../.agents/skills/fastapi-module/scripts/run_module.py"
    run(copy, [runner, "new_module", "sample_operations", "--title", "独立样例"], env)
    run(copy, ["-m", "alembic", "upgrade", "head"], env)
    run(
        copy, ["-m", "alembic", "revision", "--autogenerate", "-m", "existing module baseline"], env
    )
    run(copy, ["-m", "ruff", "format", "migrations"], env)
    before = snapshot(copy)
    run(
        copy,
        [
            runner,
            "new_operation",
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
            runner,
            "new_operation",
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
    run(copy, [runner, "new_pipeline", "sample_operations", "daily", "--title", "阶段样例"], env)
    checker = "../.agents/skills/fastapi-check/scripts/run_check.py"
    result = run(copy, [checker, "check", "--module", "sample_operations"], env)
    assert "通过  模块测试" in result and "失败  " not in result
