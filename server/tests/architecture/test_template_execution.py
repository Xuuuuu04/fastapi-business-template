"""
长样例调度不丢测试，副本类型缓存互相独立，源码变化仍由真实 mypy 检出。
"""

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


# 自动预算为主机保留CPU，未知或较小机器仍能运行并行双库。
@pytest.mark.parametrize("cpus,expected", [(None, 2), (1, 2), (4, 2), (8, 4), (10, 4), (64, 4)])
def test_automatic_worker_budget(
    cpus: int | None, expected: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("fastapi_check.arguments.os.cpu_count", lambda: cpus)
    assert default_workers() == expected


# 长短交替只改变执行顺序，串行保持原顺序，所有原对象恰好出现一次。
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


# 缓存复制而非链接，修改副本不改来源；缓存存在时源码错误仍让类型检查失败。
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

    # 最小来源只替代复制边界，不替代 mypy 的实际失效检查。
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
