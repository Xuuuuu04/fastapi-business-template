import json
from pathlib import Path

import pytest
from fastapi_check.acceptance_lifecycle import lifecycle_path, temporary_folder, write_lifecycle


def test_lifecycle_requires_a_new_report_file(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    output.write_text("existing")
    with pytest.raises(ValueError, match="新文件"):
        lifecycle_path(str(output))
    assert output.read_text() == "existing"


def test_failed_cleanup_never_writes_success(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "data"
    folder.mkdir()

    class FailedCleanup:
        name = str(folder)

        def cleanup(self) -> None:
            raise OSError("synthetic cleanup failure")

    monkeypatch.setattr(
        "fastapi_check.acceptance_lifecycle.tempfile.TemporaryDirectory",
        lambda **kwargs: FailedCleanup(),
    )
    report = tmp_path / "lifecycle.json"
    with pytest.raises(OSError, match="cleanup failure"), temporary_folder("synthetic", report):
        assert folder.exists()
    assert folder.exists()
    assert json.loads(report.read_text()) == {
        "run_id": "synthetic",
        "folder": str(folder),
        "phase": "created",
    }


def test_lifecycle_replaces_only_a_complete_json(tmp_path: Path, monkeypatch) -> None:
    report, folder = tmp_path / "lifecycle.json", tmp_path / "data"
    write_lifecycle(report, "synthetic", folder, "created")
    seen = []
    from fastapi_check import acceptance_lifecycle

    original = acceptance_lifecycle.os.replace

    def replace(source, target) -> None:
        seen.append(json.loads(Path(target).read_text())["phase"])
        assert json.loads(Path(source).read_text())["phase"] == "cleanup_complete"
        original(source, target)

    monkeypatch.setattr(acceptance_lifecycle.os, "replace", replace)
    write_lifecycle(report, "synthetic", folder, "cleanup_complete")
    assert seen == ["created"]
    assert json.loads(report.read_text())["phase"] == "cleanup_complete"
    assert list(tmp_path.glob(".acceptance-lifecycle-*")) == []
