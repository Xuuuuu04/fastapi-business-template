"""检查结果的轻量读取、轨迹完整性、旧格式转换与并发写入必须给出真实证据。"""

import gzip
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi_project.development.check_assets import expand_run
from fastapi_project.development.check_storage import load_cases
from fastapi_project.development.history import read_checks, save_check


# SQL细节只进入压缩轨迹，测试结果流保留定位所需的轻量步骤。
def record() -> dict:
    run = {
        "id": "run1",
        "operation": "sample.read",
        "status": "ok",
        "steps": [{"name": "read", "status": "ok", "database": [{"shape": "DETAIL_SQL"}]}],
    }
    return {
        "fingerprints": {},
        "passed": True,
        "source_changed": False,
        "checks": {"默认测试": True},
        "scope": {"kind": "all"},
        "suites": [
            {
                "database": "sqlite",
                "exit_code": 0,
                "cases": [
                    {"nodeid": "test_read", "outcome": "passed", "runs": [run, run]},
                ],
            }
        ],
    }


# 清单与轻量结果不嵌入SQL，重复轨迹只存一次；按需查看仍能取回原来的细节。
def test_manifest_and_content_addressed_detail(tmp_path: Path) -> None:
    path = save_check(tmp_path, record())
    assert json.loads(path.read_text())["schema_version"] == 2
    assert "DETAIL_SQL" not in path.read_text()
    [metadata] = read_checks(tmp_path, include_cases=False)
    suite = metadata["suites"][0]
    assert suite["cases"] == [] and suite["counts"] == {"passed": 1}
    [case] = load_cases(suite)
    assert "DETAIL_SQL" not in json.dumps(case)
    assert expand_run(case["runs"][0])["steps"][0]["database"][0]["shape"] == "DETAIL_SQL"
    assert len(list((path.parent / "_runs").glob("*.gz"))) == 1


# 查询摘要不需要读轨迹；真正请求细节时，丢失或损坏必须报错。
def test_missing_and_corrupt_details_are_visible(tmp_path: Path) -> None:
    path = save_check(tmp_path, record())
    run = read_checks(tmp_path)[0]["suites"][0]["cases"][0]["runs"][0]
    detail = path.parent / run["detail_ref"]["file"]
    detail.write_bytes(gzip.compress(b"{}"))
    with pytest.raises(ValueError, match="摘要"):
        expand_run(run)
    detail.unlink()
    assert read_checks(tmp_path, include_cases=False)[0]["passed"] is True
    with pytest.raises(ValueError, match="缺失"):
        expand_run(run)


# 原记录不变时索引不重读旧大JSON；索引损坏后从原证据重建。
def test_legacy_import_is_incremental_and_rebuildable(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "server/var/development/checks"
    folder.mkdir(parents=True)
    source = folder / "legacy.json"
    data = {**record(), "schema_version": 1, "id": "old", "finished_at": "2026-10-01"}
    source.write_text(json.dumps(data))
    first = read_checks(tmp_path)
    assert first[0]["imported_schema"] == 1 and source.read_text() == json.dumps(data)
    original = __import__("fastapi_project.development.check_index", fromlist=["import_legacy"])
    with monkeypatch.context() as context:
        context.setattr(original, "import_legacy", lambda *args: pytest.fail("重复读取旧JSON"))
        assert read_checks(tmp_path)[0]["id"] == "old"
    (folder / "_index.sqlite3").write_bytes(b"broken index")
    assert read_checks(tmp_path)[0]["id"] == "old"
    assert expand_run(first[0]["suites"][0]["cases"][0]["runs"][0])["id"] == "run1"


# 多个完成者独立写入，索引串行提交不丢检查，也不把同轮复制计成新结果。
def test_concurrent_results_and_imported_duplicates(tmp_path: Path) -> None:
    with ThreadPoolExecutor(max_workers=4) as pool:
        paths = list(pool.map(lambda _: save_check(tmp_path, record()), range(12)))
    assert len(read_checks(tmp_path)) == 12
    imported = tmp_path / "imported"
    shutil.copytree(paths[0].parent, imported)
    assert len(read_checks(tmp_path, [imported], include_cases=False)) == 12


# 结果流被改动不能继续提供通过证据。
def test_case_stream_integrity(tmp_path: Path) -> None:
    path = save_check(tmp_path, record())
    metadata = read_checks(tmp_path, include_cases=False)[0]
    suite = metadata["suites"][0]
    with gzip.open(path.parent / suite["case_file"], "wt") as output:
        output.write('{"nodeid":"changed","outcome":"passed","runs":[]}\n')
    with pytest.raises(ValueError, match="损坏"):
        load_cases(suite)
