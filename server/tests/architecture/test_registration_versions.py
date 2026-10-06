"""
登记变化按业务归属使结果过期；替换绑定和未知登记写法不能掩盖版本变化。
"""

from pathlib import Path

import pytest
from fastapi_project.development.history import fingerprints
from fastapi_project.development.selection import module_files

from tests.architecture.test_history_versions import LINKS, sample_project, write


# 同文件里改 router 属性不是单纯新增登记，所属包与调用方必须重测。
def test_router_binding_change_expires_owner_and_callers(tmp_path: Path) -> None:
    sample_project(tmp_path)
    names = ["sample_accounts", "sample_records", "standalone"]
    before = fingerprints(tmp_path, names, LINKS)
    path = tmp_path / "server/app/api/routers.py"
    write(path, path.read_text().replace("sample_accounts.router", "sample_accounts.other_router"))
    changed = fingerprints(tmp_path, names, LINKS)
    assert changed["sample_accounts"] != before["sample_accounts"]
    assert changed["sample_records"] != before["sample_records"]
    assert changed["standalone"] == before["standalone"]


# 总目录替换导入的实现对象，不能因仍指向相同文件就保留旧结果。
def test_catalog_binding_change_is_scoped(tmp_path: Path) -> None:
    sample_project(tmp_path)
    names = ["sample_accounts", "sample_records", "standalone"]
    before = fingerprints(tmp_path, names, LINKS)
    path = tmp_path / "server/app/setup/catalog.py"
    write(
        path,
        path.read_text().replace(
            "import module as sample_accounts", "import other_module as sample_accounts"
        ),
    )
    changed = fingerprints(tmp_path, names, LINKS)
    assert changed["sample_accounts"] != before["sample_accounts"]
    assert changed["sample_records"] != before["sample_records"]
    assert changed["standalone"] == before["standalone"]


# 动态列表和重复赋值无法证明归属，任何内容变化都按公共变化处理。
@pytest.mark.parametrize(
    "replacement", ["MODULES = build_modules()\n", "MODULES = []\nMODULES = []\n"]
)
def test_unknown_catalog_shape_is_common(tmp_path: Path, replacement: str) -> None:
    sample_project(tmp_path)
    path = tmp_path / "server/app/setup/catalog.py"
    write(path, replacement)
    names = ["sample_accounts", "sample_records"]
    before = fingerprints(tmp_path, names, LINKS)
    write(path, replacement.replace("()", "(1)").replace("[]", "[other]"))
    changed = fingerprints(tmp_path, names, LINKS)
    assert all(changed[name] != before[name] for name in names)


# 快速检查按真实登记取路由，不依赖文件名与模块名恰好一致。
def test_quick_files_follow_actual_router_registration(tmp_path: Path) -> None:
    sample_project(tmp_path)
    path = tmp_path / "server/app/api/routers.py"
    write(path, path.read_text().replace("sample_records", "files_api"))
    write(path, path.read_text().replace('"files_api":', '"sample_records":'))
    write(tmp_path / "server/app/api/v1/files_api.py", "router = None\n")
    files = module_files(("sample_records",), tmp_path / "server")
    assert "app/api/v1/files_api.py" in files
    assert "app/api/v1/sample_accounts.py" not in files
