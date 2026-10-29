import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
from fastapi_project.development.check_storage import save_record
from fastapi_project.development.evidence_retention import collect, pin
from fastapi_project.development.history import read_checks

from tests.architecture.test_check_storage import record


def history(project: Path) -> list[Path]:
    return [save_record(project, record()) for _ in range(6)]


def test_references_pins_failure_and_shared_assets(tmp_path: Path) -> None:
    paths = history(tmp_path)
    task = tmp_path / ".agents/records/tasks/example.json"
    task.parent.mkdir(parents=True)
    task.write_text(json.dumps({"checks": [paths[0].stem]}))
    pin(tmp_path, paths[1].stem, "固定样例原件")
    failed = save_record(tmp_path, record() | {"passed": False})
    plan = collect(tmp_path)
    assert paths[2].name in plan["delete"]
    assert paths[0].stem in plan["keep"] and paths[1].stem in plan["keep"]
    assert failed.stem in plan["keep"]
    assert not any(name.startswith("_runs/") for name in plan["delete"])
    result = collect(tmp_path, plan["preview_id"])
    assert result["applied"] and not paths[2].exists()
    assert len(read_checks(tmp_path)) == len(plan["keep"]) >= 5


def test_changed_reference_and_corrupt_asset_refuse_cleanup(tmp_path: Path) -> None:
    paths = history(tmp_path)
    plan = collect(tmp_path)
    (tmp_path / "README.md").write_text("验收原件：" + paths[0].stem)
    with pytest.raises(ValueError, match="预览后"):
        collect(tmp_path, plan["preview_id"])
    assert all(path.exists() for path in paths)
    suite = json.loads(paths[0].read_text())["suites"][0]
    (paths[0].parent / suite["case_file"]).write_bytes(b"broken")
    with pytest.raises(ValueError, match="损坏"):
        collect(tmp_path)
    assert all(path.exists() for path in paths)


def test_cleanup_move_failure_restores_originals(tmp_path: Path, monkeypatch) -> None:
    paths = history(tmp_path)
    plan = collect(tmp_path)
    original = Path.replace
    calls = []

    def fail_once(path: Path, target: Path) -> Path:
        calls.append(path)
        if len(calls) == 2:
            raise OSError("synthetic disk failure")
        return original(path, target)

    monkeypatch.setattr(Path, "replace", fail_once)
    with pytest.raises(OSError, match="disk"):
        collect(tmp_path, plan["preview_id"])
    assert all(path.exists() for path in paths)
    assert len(read_checks(tmp_path)) == 6


def test_cleanup_waits_for_unpublished_record(tmp_path: Path, monkeypatch) -> None:
    import fastapi_project.development.check_storage as storage

    history(tmp_path)
    entered, release, collecting = Event(), Event(), Event()
    original = storage.write_cases

    def pause(*args, **kwargs):
        value = original(*args, **kwargs)
        entered.set()
        assert release.wait(5)
        return value

    def cleanup():
        collecting.set()
        return collect(tmp_path)

    monkeypatch.setattr(storage, "write_cases", pause)
    with ThreadPoolExecutor(max_workers=2) as pool:
        writing = pool.submit(save_record, tmp_path, record())
        assert entered.wait(5)
        cleaning = pool.submit(cleanup)
        assert collecting.wait(5) and not cleaning.done()
        release.set()
        path = writing.result(timeout=5)
        plan = cleaning.result(timeout=5)
    assert path.stem in plan["keep"]
    assert len(read_checks(tmp_path)) == 7


def test_symlink_and_invalid_pin_are_rejected(tmp_path: Path) -> None:
    [path, *_] = history(tmp_path)
    with pytest.raises(ValueError, match="编号"):
        pin(tmp_path, "../outside", "错误路径")
    asset = path.parent / "_runs/link.json.gz"
    asset.symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="链接|越出"):
        collect(tmp_path)


def test_imported_filename_keeps_its_unique_assets(tmp_path: Path) -> None:
    data = record()
    data["suites"][0]["cases"][0]["runs"][0]["id"] = "unique-imported-run"
    source = save_record(tmp_path, data)
    identity = source.stem
    source.replace(source.parent / "imported-evidence.json")
    history(tmp_path)
    plan = collect(tmp_path)
    assert identity in plan["keep"]
    collect(tmp_path, plan["preview_id"])
    from fastapi_project.development.check_assets import expand_run

    imported = next(check for check in read_checks(tmp_path) if check["id"] == identity)
    run = imported["suites"][0]["cases"][0]["runs"][0]
    assert expand_run(run)["id"] == "unique-imported-run"


def test_legacy_record_and_conflicting_duplicate(tmp_path: Path) -> None:
    paths = history(tmp_path)
    legacy = record() | {"schema_version": 1, "id": "legacy", "finished_at": "2026-10-01"}
    (paths[0].parent / "legacy.json").write_text(json.dumps(legacy))
    plan = collect(tmp_path)
    assert "legacy" in plan["keep"] and "legacy.json" not in plan["delete"]
    altered = json.loads(paths[0].read_text()) | {"passed": False}
    (paths[0].parent / "conflicting-import.json").write_text(json.dumps(altered))
    with pytest.raises(ValueError, match="不同内容"):
        collect(tmp_path)
    assert all(path.exists() for path in paths)
