from pathlib import Path

import pytest
from fastapi_project.development.history import fingerprints
from fastapi_project.development.selection import module_files

from tests.architecture.test_history_versions import LINKS, sample_project, write


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


def test_quick_files_follow_actual_router_registration(tmp_path: Path) -> None:
    sample_project(tmp_path)
    path = tmp_path / "server/app/api/routers.py"
    write(path, path.read_text().replace("sample_records", "files_api"))
    write(path, path.read_text().replace('"files_api":', '"sample_records":'))
    write(tmp_path / "server/app/api/v1/files_api.py", "router = None\n")
    files = module_files(("sample_records",), tmp_path / "server")
    assert "app/api/v1/files_api.py" in files
    assert "app/api/v1/sample_accounts.py" not in files
