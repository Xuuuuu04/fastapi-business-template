import json
import shutil
import subprocess
import sys
from pathlib import Path

from fastapi_check.quality.rules import PROJECT
from fastapi_template.template.files import save_provenance
from fastapi_template.template.initialization import initialize
from fastapi_template.template.merge import apply_plan, update_plan

from shared.modules.validation.framework_lock import differences


def test_copy_retains_skills_and_uses_product_paths(tmp_path: Path) -> None:
    target = tmp_path / "product"
    initialize(PROJECT, target, "独立产品")
    assert sorted(path.name for path in (target / ".agents").iterdir()) == ["skills"]
    result = subprocess.run(
        [sys.executable, "-m", "fastapi_dev.main", "inspect"],
        cwd=target / "server",
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["modules"] == []


def test_upgrade_removes_old_tools_and_copies_skills(tmp_path: Path) -> None:
    base, source, target = [tmp_path / name for name in ("old", "new", "product")]
    for project in (base, source, target):
        (project / "server").mkdir(parents=True)
        (project / "server/pyproject.toml").write_text('[project]\nversion = "2.0.0"\n')
    for project in (base, target):
        (project / "server/tools").mkdir()
        (project / "server/tools/check.py").write_text("VERSION = 1\n")
    skill = ".agents/skills/fastapi-check/scripts/fastapi_check/check.py"
    (source / skill).parent.mkdir(parents=True)
    (source / skill).write_text("VERSION = 2\n")
    save_provenance(target, base)
    changes, _ = update_plan(target, base, source)
    assert any(item.name == "server/tools/check.py" and item.state == "delete" for item in changes)
    apply_plan(target, base, source, changes)
    assert not (target / "server/tools/check.py").exists()
    assert (target / skill).read_text() == "VERSION = 2\n"


def test_server_starts_without_project_skills(tmp_path: Path) -> None:
    target = tmp_path / "product"
    initialize(PROJECT, target, "部署样例")
    shutil.rmtree(target / ".agents")
    result = subprocess.run(
        [sys.executable, "-c", "from app.setup.web import create_app; create_app()"],
        cwd=target / "server",
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    file = target / "server/shared/modules/layout.py"
    file.write_text(file.read_text() + "\nCHANGED = True\n")
    assert any("layout.py" in name for name in differences(target / "server", include_skills=False))
