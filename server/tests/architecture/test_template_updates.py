import hashlib
import json
from pathlib import Path

import pytest
from fastapi_template.template.files import (
    FRAMEWORK_LIST,
    Manifest,
    check_base,
    managed_files,
    manifest,
    save_provenance,
)
from fastapi_template.template.merge import apply_plan, update_plan

from shared.modules.validation.framework_files import FRAMEWORK, REGISTRATION, SUFFIXES

LISTING = f"FRAMEWORK = {FRAMEWORK!r}\nREGISTRATION = {REGISTRATION!r}\nSUFFIXES = {SUFFIXES!r}\n"


def test_update_preserves_product_files(tmp_path: Path) -> None:
    base, source, target = projects(tmp_path)
    write(base, "server/shared/a.py", "VALUE = 1\n")
    write(source, "server/shared/a.py", "VALUE = 2\n")
    write(target, "server/shared/a.py", "VALUE = 1\n")
    protected = {
        "server/service/customer_contact/flow.py": "BUSINESS = True\n",
        "server/migrations/versions/customer.py": "REVISION = 'mine'\n",
        "server/.env": "PRIVATE = keep\n",
        "doc/notes.md": "product notes",
    }
    for name, content in protected.items():
        write(target, name, content)
    write(source, "server/service/customer_contact/flow.py", "UPSTREAM = True\n")
    write(source, "server/migrations/versions/customer.py", "UPSTREAM = True\n")
    before = {name: (target / name).read_bytes() for name in protected}
    save_provenance(target, base)
    changes, manual = update_plan(target, base, source)
    assert [(change.name, change.state) for change in changes] == [("server/shared/a.py", "update")]
    apply_plan(target, base, source, changes)
    assert (target / "server/shared/a.py").read_text() == "VALUE = 2\n"
    assert all((target / name).read_bytes() == content for name, content in before.items())
    assert (target / "server/pyproject.toml").read_bytes() == (
        base / "server/pyproject.toml"
    ).read_bytes()
    check_base(target, source)


def test_independent_edits_merge_and_next_update(tmp_path: Path) -> None:
    base, source, target = projects(tmp_path)
    original = "first = 1\n\nmiddle = 1\n\nlast = 1\n"
    write(base, "server/shared/a.py", original)
    write(source, "server/shared/a.py", original.replace("first = 1", "first = 2"))
    write(target, "server/shared/a.py", original.replace("last = 1", "last = 3"))
    save_provenance(target, base)
    changes, _ = update_plan(target, base, source)
    assert changes[0].state == "merged"
    apply_plan(target, base, source, changes)
    assert (target / "server/shared/a.py").read_text() == "first = 2\n\nmiddle = 1\n\nlast = 3\n"
    later = tmp_path / "later"
    write(later, "server/pyproject.toml", '[project]\nversion = "2.0.0"\n')
    write(later, FRAMEWORK_LIST, LISTING)
    write(later, "server/shared/a.py", original.replace("first = 1", "first = 4"))
    changes, _ = update_plan(target, source, later)
    apply_plan(target, source, later, changes)
    assert "first = 4" in (target / "server/shared/a.py").read_text()
    assert "last = 3" in (target / "server/shared/a.py").read_text()


def test_conflict_keeps_every_file_unchanged(tmp_path: Path) -> None:
    base, source, target = projects(tmp_path)
    for root, value in ((base, 1), (source, 2), (target, 3)):
        write(root, "server/shared/a.py", f"VALUE = {value}\n")
    write(base, "server/shared/b.py", "VALUE = 1\n")
    write(source, "server/shared/b.py", "VALUE = 2\n")
    write(target, "server/shared/b.py", "VALUE = 1\n")
    save_provenance(target, base)
    before = managed_files(target)
    origin = (target / "template-source.json").read_bytes()
    changes, _ = update_plan(target, base, source)
    assert any(change.state == "conflict" for change in changes)
    with pytest.raises(ValueError, match="冲突"):
        apply_plan(target, base, source, changes)
    assert managed_files(target) == before
    assert (target / "template-source.json").read_bytes() == origin


@pytest.mark.parametrize(
    "old,local,new,state",
    [
        (None, "mine", "new", "conflict"),
        ("old", "mine", None, "conflict"),
        ("old", None, "new", "conflict"),
        ("old", "old", None, "delete"),
        (None, None, "new", "update"),
    ],
)
def test_add_delete_conflicts(
    tmp_path: Path, old: str | None, local: str | None, new: str | None, state: str
) -> None:
    base, source, target = projects(tmp_path)
    for root, content in ((base, old), (target, local), (source, new)):
        if content is not None:
            write(root, "server/shared/a.py", content)
    save_provenance(target, base)
    changes, _ = update_plan(target, base, source)
    assert len(changes) == 1 and changes[0].state == state


def test_wrong_base_and_changed_preview(tmp_path: Path) -> None:
    base, source, target = projects(tmp_path)
    for root, value in ((base, 1), (source, 2), (target, 1)):
        write(root, "server/shared/a.py", f"VALUE = {value}\n")
    save_provenance(target, base)
    with pytest.raises(ValueError, match="不一致：server/shared/a.py 等 1 个文件.*2.0.0"):
        check_base(target, source)
    changes, _ = update_plan(target, base, source)
    write(target, "server/shared/a.py", "VALUE = 3\n")
    with pytest.raises(ValueError, match="预览后"):
        apply_plan(target, base, source, changes)


@pytest.mark.parametrize(
    "local,state",
    [(None, "update"), ("HELPER = 1\n", None), ("MINE = 1\n", "conflict")],
)
def test_source_manifest_adds_newly_managed_files(
    tmp_path: Path, local: str | None, state: str | None
) -> None:
    base, source, target = projects(tmp_path)
    old_lock = 'FRAMEWORK = ("shared",)\nREGISTRATION = ()\nSUFFIXES = (".py",)\n'
    new_lock = old_lock.replace('("shared",)', '("shared", "tests/helper.py")')
    for root, text in ((base, old_lock), (target, old_lock), (source, new_lock)):
        write(root, FRAMEWORK_LIST, text)
    for root in (base, source):
        write(root, "server/tests/helper.py", "HELPER = 1\n")
    if local is not None:
        write(target, "server/tests/helper.py", local)
    digest = hashlib.sha256(old_lock.encode()).hexdigest()
    origin = {
        "schema_version": 1,
        "version": "2.0.0",
        "revision": "",
        "files": {FRAMEWORK_LIST: digest},
    }
    write(target, "template-source.json", json.dumps(origin))
    assert check_base(target, base, manifest(source)) == ["server/tests/helper.py"]
    changes, _ = update_plan(target, base, source)
    states = {change.name: change.state for change in changes}
    assert states.pop(FRAMEWORK_LIST) == "update"
    assert states.get("server/tests/helper.py") == state
    if state == "conflict":
        return
    apply_plan(target, base, source, changes)
    assert (target / "server/tests/helper.py").read_text() == "HELPER = 1\n"
    recorded = json.loads((target / "template-source.json").read_text())
    assert "server/tests/helper.py" in recorded["files"]
    assert check_base(target, source) == []


def test_symlink_is_rejected(tmp_path: Path) -> None:
    base, source, target = projects(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (target / "server/devtools").symlink_to(outside, target_is_directory=True)
    write(source, "server/devtools/a.py", "NEW = True\n")
    save_provenance(target, base)
    with pytest.raises(ValueError, match="越出项目"):
        update_plan(target, base, source)
    assert not list(outside.iterdir())


def test_dependencies_require_manual_review(tmp_path: Path) -> None:
    base, source, target = projects(tmp_path)
    write(source, "server/pyproject.toml", '[project]\nversion = "2.1.0"\n')
    save_provenance(target, base)
    _, manual = update_plan(target, base, source)
    assert manual == ["server/pyproject.toml"]


def projects(tmp_path: Path) -> tuple[Path, Path, Path]:
    roots = tuple(tmp_path / name for name in ("base", "source", "target"))
    for root in roots:
        write(root, "server/pyproject.toml", '[project]\nversion = "2.0.0"\n')
        write(root, FRAMEWORK_LIST, LISTING)
    return roots


def write(root: Path, name: str, content: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_business_document_stays_with_product(tmp_path: Path) -> None:
    write(tmp_path, ".agents/skills/fastapi-business/SKILL.md", "# 业务\n")
    write(tmp_path, ".agents/skills/fastapi-business/business.md", "# 产品业务\n")
    write(tmp_path, ".agents/skills/fastapi-business/business/order.md", "# 订单\n")
    files = managed_files(tmp_path, Manifest(("../.agents/skills",), REGISTRATION, (".md",)))
    assert list(files) == [".agents/skills/fastapi-business/SKILL.md"]


def test_update_requires_provenance_and_listing(tmp_path: Path) -> None:
    base, source, target = projects(tmp_path)
    with pytest.raises(ValueError, match="template-source.json"):
        update_plan(target, base, source)
    write(target, "template-source.json", json.dumps({"version": "2.0.0", "files": {}}))
    with pytest.raises(ValueError, match="schema_version、revision"):
        check_base(target, base)
    (source / FRAMEWORK_LIST).unlink()
    with pytest.raises(ValueError, match="框架清单"):
        manifest(source)
