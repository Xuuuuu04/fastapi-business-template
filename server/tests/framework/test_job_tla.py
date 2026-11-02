import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from fastapi_check import job_model_sources, job_tla


def result(code: int, output: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], code, stdout=output, stderr="")


def test_tlc_mutation_must_fail_for_the_named_property() -> None:
    assert (
        job_tla.checked_output(
            result(12, "Invariant CurrentAttemptOnly is violated.\n19 distinct states found"), True
        )
        == "19"
    )
    for code, output in [
        (0, "Model checking completed. No error has been found."),
        (75, "Invariant CurrentAttemptOnly is violated."),
        (12, "Invariant TypeOK is violated."),
    ]:
        with pytest.raises(ValueError, match="指定"):
            job_tla.checked_output(result(code, output), True)


def test_tlc_normal_model_requires_successful_completed_search() -> None:
    assert (
        job_tla.checked_output(
            result(
                0, "Model checking completed. No error has been found.\n19 distinct states found"
            ),
            False,
        )
        == "19"
    )
    for code, output in [
        (0, "started"),
        (12, "Model checking completed. No error has been found."),
    ]:
        with pytest.raises(ValueError, match="未通过"):
            job_tla.checked_output(result(code, output), False)


def test_tool_digest_is_pinned_without_downloading(tmp_path: Path, monkeypatch) -> None:
    jar = tmp_path / "tool.jar"
    jar.write_bytes(b"synthetic-tool")
    manifest = {"version": "fixed", "sha256": hashlib.sha256(jar.read_bytes()).hexdigest()}
    (tmp_path / "job_tlc_tool.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(job_tla, "ASSETS", tmp_path)
    assert job_tla.check_tool(jar) == "fixed"
    jar.write_bytes(b"different")
    with pytest.raises(ValueError, match="摘要不符"):
        job_tla.check_tool(jar)


def test_mapped_source_changes_or_disappears_require_review(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.py"
    source.write_text("def commit():\n    return 1\n")
    mapping = tmp_path / "mapping.json"
    mapping.write_text(
        json.dumps(
            [
                {
                    "file": "source.py",
                    "symbol": "commit",
                    "sha256": job_model_sources.source_hash(source, "commit"),
                }
            ]
        )
    )
    monkeypatch.setattr(job_model_sources, "ROOT", tmp_path)
    monkeypatch.setattr(job_model_sources, "MAPPING", mapping)
    job_model_sources.require_mapping()
    source.write_text("def commit():\n    return 2\n")
    with pytest.raises(ValueError, match="source.py:commit"):
        job_model_sources.require_mapping()
    source.unlink()
    with pytest.raises(ValueError, match="source.py:commit"):
        job_model_sources.require_mapping()


def verification_fixture(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(job_tla, "ROOT", tmp_path)
    monkeypatch.setattr(job_tla, "require_mapping", lambda: None)
    monkeypatch.setattr(job_tla, "input_hashes", lambda: {"model": "same"})
    monkeypatch.setattr(job_tla, "check_tool", lambda jar: "fixed")
    monkeypatch.setattr(job_tla, "run_tlc", lambda *args: "19")
    monkeypatch.setattr(job_tla, "run_implementation", lambda output: None)


def test_success_report_needs_both_models_and_real_regression(tmp_path: Path, monkeypatch) -> None:
    verification_fixture(tmp_path, monkeypatch)
    stages = []
    monkeypatch.setattr(job_tla, "run_tlc", lambda jar, output, broken: stages.append(broken))
    monkeypatch.setattr(
        job_tla, "run_implementation", lambda output: stages.append("implementation")
    )
    output = job_tla.verify_tlc(tmp_path / "tool.jar")
    report = json.loads((output / "result.json").read_text())
    assert stages == [False, True, "implementation"]
    assert report["status"] == "通过" and report["implementation"] == "通过"


@pytest.mark.parametrize("drift", ["sources", "model"])
def test_changes_during_verification_are_reported_as_failure(
    tmp_path: Path, monkeypatch, drift
) -> None:
    verification_fixture(tmp_path, monkeypatch)
    reads = []

    def mapping() -> None:
        reads.append(1)
        if len(reads) > 1:
            raise ValueError("source drift")

    if drift == "sources":
        monkeypatch.setattr(job_tla, "require_mapping", mapping)
    else:
        hashes = iter([{"model": "before"}, {"model": "after"}])
        monkeypatch.setattr(job_tla, "input_hashes", lambda: next(hashes))
    with pytest.raises(ValueError):
        job_tla.verify_tlc(tmp_path / "tool.jar")
    reports = list((tmp_path / "var/formal").glob("*/result.json"))
    assert len(reports) == 1
    assert json.loads(reports[0].read_text())["status"] == "失败"


def test_tlc_timeout_keeps_output_and_fails(tmp_path: Path, monkeypatch) -> None:
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("java", 60, output=b"partial search")

    monkeypatch.setattr(job_tla.subprocess, "run", timeout)
    with pytest.raises(ValueError, match="60 秒"):
        job_tla.run_tlc(tmp_path / "tool.jar", tmp_path, False)
    assert (tmp_path / "model.log").read_text() == "partial search"
