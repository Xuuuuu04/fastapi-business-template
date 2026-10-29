from pathlib import Path

from fastapi_check.quality.rules import PROJECT
from fastapi_template.template.initialization import initialize

from shared.records.version import source_version


def test_source_version_tracks_code_not_history(tmp_path: Path) -> None:
    target = tmp_path / "product"
    initialize(PROJECT, target, "版本样例")
    root = target / "server"
    before = source_version(root)
    (target / "doc/notes.md").write_text("新工作\n", encoding="utf-8")
    (root / "var").mkdir()
    (root / "var/check.json").write_text("{}", encoding="utf-8")
    assert source_version(root) == before
    source = root / "app/setup/catalog.py"
    source.write_text(source.read_text() + "\nCHANGED = True\n", encoding="utf-8")
    assert source_version(root) != before
