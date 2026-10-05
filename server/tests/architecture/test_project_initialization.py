"""
新产品初始化不会带上模板的讨论、验收、任务历史、数据库或环境。
产品计划重新开始，保留的框架可继续生成业务模块并接受升级。
"""

import json
import subprocess
from pathlib import Path

import pytest
from dotenv import dotenv_values

from tools.development.history import read_checks
from tools.quality.rules import PROJECT
from tools.template.files import check_base
from tools.template.initialization import initialize


# 真实模板副本包含可复用代码，产品入口和计划原生，历史结果不进入新产品。
def test_native_product_copy(tmp_path: Path) -> None:
    target = tmp_path / "product"
    initialize(PROJECT, target, "客户联系产品")
    for name in ("design", ".git", ".agents", "server/.env", "server/.venv", "server/var"):
        assert not (target / name).exists()
    assert "客户联系产品" in (target / "AGENTS.md").read_text(encoding="utf-8")
    assert "已完成" not in (target / "doc/tasks.md").read_text(encoding="utf-8")
    assert "验收记录" not in (target / "server/deploy/README.md").read_text(encoding="utf-8")
    plan = json.loads((target / "project-plan.json").read_text(encoding="utf-8"))
    assert plan["lines"] == [] and plan["name"] == "客户联系产品"
    assert dotenv_values(target / "server/.env.example")["APP_NAME"] == "客户联系产品"
    assert read_checks(target) == []
    check_base(target, PROJECT)
    result = subprocess.run(
        ["uv", "lock", "--check", "--offline"],
        cwd=target / "server",
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode()


# 现有目录和模板自己的子目录不能作为目标，防止覆盖与递归复制。
def test_initialization_rejects_existing_directory(tmp_path: Path) -> None:
    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "owned.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError):
        initialize(PROJECT, existing, "产品")
    assert (existing / "owned.txt").read_text() == "keep"
    with pytest.raises(ValueError):
        initialize(PROJECT, PROJECT / "nested-product", "产品")
