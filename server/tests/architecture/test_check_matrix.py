"""
数据库矩阵、总预算、缓存来源与并行结果汇总不能混淆实际检查范围。
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi_check.cache import cached_round, execution_profile
from fastapi_check.matrix import CheckOptions, databases, execute_matrix
from fastapi_project.development.history import save_check


# 两个数据库平分预算，各自资源编号不同，控制连接不泄漏到SQLite轮。
def test_parallel_budget_and_distinct_resources() -> None:
    recorded = []

    # 替身只观察每个进程会收到什么，不真的连接数据库。
    def run(title, arguments, environment, database):
        recorded.append((arguments, environment, database))
        return True, {"database": database, "exit_code": 0, "cases": []}

    outcomes = execute_matrix(
        ("sqlite", "postgresql"),
        "postgresql://test.invalid/control",
        ["-m", "pytest"],
        {},
        CheckOptions(workers=4),
        run,
    )
    assert [result[0] for result in outcomes] == ["sqlite", "postgresql"]
    assert all(arguments[-2:] == ["-n", "2"] for arguments, _, _ in recorded)
    assert all("--dist=worksteal" in arguments for arguments, _, _ in recorded)
    assert len({env["APP_TEST_RUN_ID"] for _, env, _ in recorded}) == 2
    assert "APP_TEST_CONTROL_URL" not in next(env for _, env, db in recorded if db == "sqlite")


# 模型和数据库凭据不进入检查配置摘要，配置变化仍让缓存失效。
def test_profile_is_private_and_changes_with_services(monkeypatch) -> None:
    first = execution_profile(CheckOptions(), "postgresql://user:secret-a@test.invalid/control")
    second = execution_profile(CheckOptions(), "postgresql://user:secret-b@test.invalid/control")
    assert first != second and "secret-a" not in json.dumps(first)


# 最近失败不能被旧的通过掩盖，源码变化也不能沿用通过记录。
def test_cache_preserves_failure_and_version(tmp_path: Path) -> None:
    value = {
        "fingerprints": {},
        "system_fingerprint": "s1",
        "source_changed": False,
        "scope": {"kind": "all"},
        "execution_profile": {},
        "passed": True,
        "checks": {"默认测试": True},
        "suites": [],
    }
    save_check(tmp_path, value)
    assert cached_round(tmp_path, {}, "s1", {"kind": "all"}, {})
    assert not cached_round(tmp_path, {}, "s2", {"kind": "all"}, {})
    save_check(tmp_path, {**value, "passed": False})
    assert not cached_round(tmp_path, {}, "s1", {"kind": "all"}, {})


# 真实xdist子进程结束时输出全部worker的case，不由最后写文件的worker覆盖。
def test_parallel_results_are_combined(tmp_path: Path) -> None:
    tests = tmp_path / "test_items.py"
    tests.write_text(
        'import pytest\n@pytest.mark.parametrize("n",range(12))\n'
        "def test_value(n):\n    assert n >= 0\n"
    )
    target = tmp_path / "result.json"
    environment = {key: value for key, value in os.environ.items() if not key.startswith("APP_")}
    environment["APP_DEVELOPMENT_RESULT"] = str(target)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--dist=worksteal",
            "-n",
            "2",
            "--confcutdir",
            str(tmp_path),
            "-p",
            "tests.development_history",
            str(tests),
        ],
        env=environment,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(target.read_text())
    assert len(data["cases"]) == 12 and data["exit_code"] == 0


# 无明确地址不能假装已经运行了PostgreSQL。
def test_database_selection_requires_target() -> None:
    with pytest.raises(ValueError):
        databases("", "both")
    assert databases("", "sqlite") == ("sqlite",)
