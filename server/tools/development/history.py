"""
保存真实检查结果，并用文件摘要判断它是否仍适用于当前代码。
记录只保存测试名称、状态和执行过的操作；不保存环境变量、连接地址或业务数据。
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EXCLUDED = {"__pycache__", ".venv", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
COMMON = (
    "shared",
    "tools",
    "app",
    "tests/framework",
    "tests/architecture",
    "tests/quality",
    "tests/security",
    "tests/contracts",
    "tests/recovery",
    "tests/conftest.py",
    "tests/failure_reports.py",
    "tests/development_history.py",
    "tests/testing_app.py",
    "pyproject.toml",
    "uv.lock",
    "migrations",
)


# 按路径和原始内容计算摘要；修改、增加、删除都会改变结果。
def fingerprint(paths: list[Path], root: Path) -> str:
    digest = hashlib.sha256()
    files: set[Path] = set()
    for path in paths:
        files.update([path] if path.is_file() else path.rglob("*"))
    for path in sorted(files):
        if path.is_file() and not EXCLUDED.intersection(path.relative_to(root).parts):
            digest.update(path.relative_to(root).as_posix().encode() + b"\0")
            digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()


# 模块测试同时受公共代码、模块代码、业务规则及本模块测试影响。
def fingerprints(project: Path, modules: list[str]) -> dict[str, str]:
    server = project / "server"
    common = [server / name for name in COMMON]
    return {
        name: fingerprint(
            common
            + [
                server / "service" / name,
                project / "doc" / name / "rules.md",
                project / "doc" / name / "needs.md",
                server / "tests/modules" / name,
                server / "tests/integration" / name,
            ],
            project,
        )
        for name in modules
    }


# 原子保存一轮检查，独立编号避免并行工作覆盖彼此的结果。
def save_check(project: Path, record: dict[str, Any]) -> Path:
    folder = project / "server" / "var" / "development" / "checks"
    folder.mkdir(parents=True, exist_ok=True)
    identity = uuid.uuid4().hex
    record = {
        **record,
        "schema_version": 1,
        "id": identity,
        "finished_at": datetime.now(UTC).isoformat(),
    }
    path = folder / f"{identity}.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


# 读取已保留的轮次；损坏记录直接报错，不悄悄当成没有测试。
def read_checks(project: Path, extra: list[Path] | None = None) -> list[dict[str, Any]]:
    folder = project / "server" / "var" / "development" / "checks"
    files = {path.resolve() for path in folder.glob("*.json")}
    for directory in extra or []:
        if not directory.is_dir():
            raise ValueError(f"检查记录目录不存在：{directory}")
        files |= {path.resolve() for path in directory.glob("*.json")}
    checks: dict[str, dict[str, Any]] = {}
    for path in files:
        check = json.loads(path.read_text(encoding="utf-8"))
        if check.get("schema_version") != 1:
            raise ValueError(f"检查记录格式不支持：{path}")
        identity = check.get("id") or hashlib.sha256(path.read_bytes()).hexdigest()
        if identity in checks and checks[identity] != check:
            raise ValueError(f"同一轮检查内容不一致：{path}")
        checks[identity] = check
    return sorted(checks.values(), key=lambda check: check["finished_at"])


# 每种数据库分别取最近一轮，旧版本结果保留但明确显示过期。
def module_checks(checks: list[dict[str, Any]], module: str, current: str) -> dict[str, Any]:
    selected = [check for check in checks if module in check["fingerprints"]]
    latest: dict[str, Any] = {}
    for check in selected:
        for suite in check["suites"]:
            latest[suite["database"]] = {
                **suite,
                "finished_at": check["finished_at"],
                "current": check["fingerprints"][module] == current and not check["source_changed"],
                "checks_passed": check["passed"],
            }
    return {"rounds": len(selected), "latest": latest}
