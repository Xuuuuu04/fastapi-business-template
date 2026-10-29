import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi_check.arguments import default_workers

from tests.scheduling import LONG_TESTS, schedule
from tests.template_project import initialize


@pytest.mark.parametrize("cpus,expected", [(None, 2), (1, 2), (4, 2), (8, 4), (10, 4), (64, 4)])
def test_automatic_worker_budget(
    cpus: int | None, expected: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("fastapi_check.arguments.os.cpu_count", lambda: cpus)
    assert default_workers() == expected


def test_scheduling_preserves_every_case(monkeypatch: pytest.MonkeyPatch) -> None:
    items = [SimpleNamespace(name=name) for name in ("a", "b", *reversed(LONG_TESTS))]
    original = items.copy()
    monkeypatch.setenv("APP_TEST_WORKERS", "0")
    schedule(cast(Any, items))
    assert items == original
    monkeypatch.setenv("APP_TEST_WORKERS", "4")
    schedule(cast(Any, items))
    assert {id(item) for item in items} == {id(item) for item in original}
    assert len(items) == len(original)
    assert [item.name for item in items[:4]] == [LONG_TESTS[0], "a", LONG_TESTS[1], "b"]


def test_copied_type_cache_is_independent_and_invalidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    server = source / "server"
    server.mkdir(parents=True)
    code = server / "example.py"
    code.write_text("value: int = 1\n")
    command = [sys.executable, "-m", "mypy", "--cache-dir", ".mypy_cache", "example.py"]
    environment = {key: value for key, value in os.environ.items() if not key.startswith("APP_")}
    first = subprocess.run(command, cwd=server, env=environment, capture_output=True)
    assert first.returncode == 0, first.stdout

    def create(source: Path, target: Path, name: str) -> None:
        (target / "server").mkdir(parents=True)
        (target / "server/example.py").write_bytes((source / "server/example.py").read_bytes())

    monkeypatch.setattr("tests.template_project.initialize_project", create)
    target = tmp_path / "copy"
    initialize(source, target, "合成类型检查")
    marker = target / "server/.mypy_cache/marker"
    marker.write_text("独立副本")
    assert not (server / ".mypy_cache/marker").exists()
    (target / "server/example.py").write_text('value: int = "错误"\n')
    failed = subprocess.run(command, cwd=target / "server", env=environment, capture_output=True)
    assert failed.returncode == 1 and b"Incompatible types" in failed.stdout
    assert code.read_text() == "value: int = 1\n"
