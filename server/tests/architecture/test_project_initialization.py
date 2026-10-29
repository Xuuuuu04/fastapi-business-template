import json
import subprocess
from pathlib import Path

import pytest
from dotenv import dotenv_values
from fastapi_check.quality.rules import PROJECT
from fastapi_project.development.history import read_checks
from fastapi_template.template.files import check_base
from fastapi_template.template.initialization import initialize


def test_native_product_copy(tmp_path: Path) -> None:
    target = tmp_path / "product"
    initialize(PROJECT, target, "客户联系产品")
    for name in ("design", ".git", "server/.env", "server/.venv", "server/var"):
        assert not (target / name).exists()
    assert (target / ".agents/skills/fastapi-template/SKILL.md").is_file()
    agents = (target / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.startswith("# 客户联系产品\n")
    readme = (target / "README.md").read_text(encoding="utf-8")
    assert "uv run dev status --summary --json" in readme and "scripts/run_" not in readme
    assert (target / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"
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


def test_initialization_rejects_existing_directory(tmp_path: Path) -> None:
    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "owned.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError):
        initialize(PROJECT, existing, "产品")
    assert (existing / "owned.txt").read_text() == "keep"
    with pytest.raises(ValueError):
        initialize(PROJECT, PROJECT / "nested-product", "产品")
