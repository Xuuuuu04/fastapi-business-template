from pathlib import Path

from fastapi_template.template.files import save_provenance
from fastapi_template.template.merge import apply_plan, update_plan


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
