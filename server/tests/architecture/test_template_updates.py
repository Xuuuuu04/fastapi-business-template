"""
框架增量更新的业务保护：独立修改可合并，冲突时全部保留，
业务目录、迁移历史、配置与依赖文件不会被框架文件覆盖。
"""

import hashlib
import json
from pathlib import Path

import pytest
from fastapi_template.template.files import (
    LOCK_MODULE,
    check_base,
    managed_files,
    manifest,
    save_provenance,
)
from fastapi_template.template.merge import apply_plan, update_plan


# 新版改公共文件，产品自己的模块、迁移、依赖与环境必须保持。
def test_update_preserves_product_files(tmp_path: Path) -> None:
    base, source, target = projects(tmp_path)
    write(base, "server/shared/a.py", "VALUE = 1\n")
    write(source, "server/shared/a.py", "VALUE = 2\n")
    write(target, "server/shared/a.py", "VALUE = 1\n")
    protected = {
        "server/service/customer_contact/flow.py": "BUSINESS = True\n",
        "server/migrations/versions/customer.py": "REVISION = 'mine'\n",
        "server/.env": "PRIVATE = keep\n",
        "project-plan.json": "product plan",
        "doc/tasks.md": "product tasks",
        "server/framework.lock": "original lock",
    }
    for name, content in protected.items():
        write(target, name, content)
    write(source, "server/service/customer_contact/flow.py", "UPSTREAM = True\n")
    write(source, "server/migrations/versions/customer.py", "UPSTREAM = True\n")
    before = {name: (target / name).read_bytes() for name in protected}
    changes, manual = update_plan(target, base, source)
    assert [(change.name, change.state) for change in changes] == [("server/shared/a.py", "update")]
    apply_plan(target, base, source, changes)
    assert (target / "server/shared/a.py").read_text() == "VALUE = 2\n"
    assert all((target / name).read_bytes() == content for name, content in before.items())
    assert (target / "server/pyproject.toml").read_bytes() == (
        base / "server/pyproject.toml"
    ).read_bytes()
    check_base(target, source)


# 两边改动不同段时保留产品修改，并使第二次更新继续使用正确的新版来源。
def test_independent_edits_merge_and_next_update(tmp_path: Path) -> None:
    base, source, target = projects(tmp_path)
    original = "first = 1\n\nmiddle = 1\n\nlast = 1\n"
    write(base, "server/shared/a.py", original)
    write(source, "server/shared/a.py", original.replace("first = 1", "first = 2"))
    write(target, "server/shared/a.py", original.replace("last = 1", "last = 3"))
    changes, _ = update_plan(target, base, source)
    assert changes[0].state == "merged"
    apply_plan(target, base, source, changes)
    assert (target / "server/shared/a.py").read_text() == "first = 2\n\nmiddle = 1\n\nlast = 3\n"
    later = tmp_path / "later"
    write(later, "server/pyproject.toml", '[project]\nversion = "2.0.0"\n')
    write(later, "server/shared/a.py", original.replace("first = 1", "first = 4"))
    changes, _ = update_plan(target, source, later)
    apply_plan(target, source, later, changes)
    assert "first = 4" in (target / "server/shared/a.py").read_text()
    assert "last = 3" in (target / "server/shared/a.py").read_text()


# 一个冲突必须阻止同批其他正常文件写入，来源记录也保持原样。
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


# 新增重名、修改与删除冲突不可自动覆盖；只删除产品没有修改的上游删除项。
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
    changes, _ = update_plan(target, base, source)
    assert len(changes) == 1 and changes[0].state == state


# 旧模板不一致和预览后再次修改都阻止保存。
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


# 升级用新模板自己的清单：旧工具写的来源记录没登记的文件单独列出、按新增处理，
# 来源记录换成新格式（含 framework_lock），下次升级不再被拒绝。
@pytest.mark.parametrize(
    "local,state",
    [(None, "update"), ("HELPER = 1\n", None), ("MINE = 1\n", "conflict")],
)
def test_source_manifest_adds_newly_managed_files(
    tmp_path: Path, local: str | None, state: str | None
) -> None:
    base, source, target = projects(tmp_path)
    old_lock = 'LOCKED = ("shared",)\nREGISTRATION = ()\nSUFFIXES = (".py",)\n'
    new_lock = old_lock.replace('("shared",)', '("shared", "tests/helper.py")')
    for root, text in ((base, old_lock), (target, old_lock), (source, new_lock)):
        write(root, LOCK_MODULE, text)
    for root in (base, source):
        write(root, "server/tests/helper.py", "HELPER = 1\n")
    if local is not None:
        write(target, "server/tests/helper.py", local)
    write(source, "server/framework.lock", "{}\n")
    digest = hashlib.sha256(old_lock.encode()).hexdigest()
    origin = {"version": "2.0.0", "files": {LOCK_MODULE: digest}}
    write(target, "template-source.json", json.dumps(origin))
    assert check_base(target, base, manifest(source)) == ["server/tests/helper.py"]
    changes, _ = update_plan(target, base, source)
    states = {change.name: change.state for change in changes}
    assert states.pop(LOCK_MODULE) == "update"
    assert states.get("server/tests/helper.py") == state
    if state == "conflict":
        return
    apply_plan(target, base, source, changes)
    assert (target / "server/tests/helper.py").read_text() == "HELPER = 1\n"
    recorded = json.loads((target / "template-source.json").read_text())
    assert "server/tests/helper.py" in recorded["files"]
    assert recorded["framework_lock"] == hashlib.sha256(b"{}\n").hexdigest()
    assert check_base(target, source) == []


# 模板和产品链接均不能把写入引向项目之外。
def test_symlink_is_rejected(tmp_path: Path) -> None:
    base, source, target = projects(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (target / "server/shared").symlink_to(outside, target_is_directory=True)
    write(source, "server/shared/a.py", "NEW = True\n")
    with pytest.raises(ValueError):
        update_plan(target, base, source)
    assert not list(outside.iterdir())


# 依赖变化明确列出，不能静默忽略或复制到产品。
def test_dependencies_require_manual_review(tmp_path: Path) -> None:
    base, source, target = projects(tmp_path)
    write(source, "server/pyproject.toml", '[project]\nversion = "2.1.0"\n')
    _, manual = update_plan(target, base, source)
    assert manual == ["server/pyproject.toml"]


# 建立三个独立版本，没有 Git 共同祖先也可以比较。
def projects(tmp_path: Path) -> tuple[Path, Path, Path]:
    roots = tuple(tmp_path / name for name in ("base", "source", "target"))
    for root in roots:
        write(root, "server/pyproject.toml", '[project]\nversion = "2.0.0"\n')
    return roots


# 保存明确样例，不访问真实项目或数据库。
def write(root: Path, name: str, content: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
