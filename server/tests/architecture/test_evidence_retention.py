"""
证据清理必须保留引用、失败历史与共享轨迹，预览变化和并发发布不能造成原件丢失。
"""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
from fastapi_project.development.check_storage import save_record
from fastapi_project.development.evidence_retention import collect, pin
from fastapi_project.development.history import read_checks

from tests.architecture.test_check_storage import record


# 六轮同源码成功中仅三轮可保留，其余按显式引用与失败历史补足。
def history(project: Path) -> list[Path]:
    return [save_record(project, record()) for _ in range(6)]


# 被任务、手写文档和显式固定引用的历史保留，未引用的旧轮可清理且共享轨迹仍存在。
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


# 文档引用在预览后增加必须使旧计划失效，失败不删除任何原件。
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


# 普通磁盘错误时回滚已经移走的清单及结果流，不留下半次清理。
def test_cleanup_move_failure_restores_originals(tmp_path: Path, monkeypatch) -> None:
    paths = history(tmp_path)
    plan = collect(tmp_path)
    original = Path.replace
    calls = []

    # 第二次移动模拟磁盘错误，回滚动作仍使用真实文件操作。
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


# 写入共享对象之后、发布清单之前暂停，清理必须等待发布锁而不能删除新对象。
def test_cleanup_waits_for_unpublished_record(tmp_path: Path, monkeypatch) -> None:
    import fastapi_project.development.check_storage as storage

    history(tmp_path)
    entered, release, collecting = Event(), Event(), Event()
    original = storage.write_cases

    # 对象和结果流真正保存后暂停，只模拟发布的时间窗口。
    def pause(*args, **kwargs):
        value = original(*args, **kwargs)
        entered.set()
        assert release.wait(5)
        return value

    # 清理发起信号在调用前给出，不依赖工作线程执行顺序猜测。
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


# 证据链接和非法编号不允许参与清理或固定。
def test_symlink_and_invalid_pin_are_rejected(tmp_path: Path) -> None:
    [path, *_] = history(tmp_path)
    with pytest.raises(ValueError, match="编号"):
        pin(tmp_path, "../outside", "错误路径")
    asset = path.parent / "_runs/link.json.gz"
    asset.symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="链接|越出"):
        collect(tmp_path)


# 自定义导入文件名仍拥有独立轨迹，不能因不符合新编号文件名而被当作孤立对象清理。
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


# 同编号不同事实不能合并成单轮通过；旧格式清单和转换资产也保持可查。
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
