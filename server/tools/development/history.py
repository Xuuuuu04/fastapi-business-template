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

from tools.development.versions import (
    EXCLUDED,
    REGISTRATIONS,
    ROUTERS_FILE,
    V1_FOLDER,
    Reader,
    registration_entry,
    registration_parts,
    route_ownership,
)

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


# 调用方包含被调用模块的版本，间接调用与后台任务也不能沿用旧检查。
def dependency_modules(name: str, links: dict[str, dict[str, list[str]]]) -> list[str]:
    pending = [name]
    found: set[str] = set()
    while pending:
        module = pending.pop()
        if module not in found:
            found.add(module)
            pending.extend(links.get(module, {}))
    return sorted(found)


# 每个模块的业务代码、确认规则和测试共同决定它的检查版本。
def module_paths(project: Path, name: str) -> list[Path]:
    server = project / "server"
    return [
        server / "service" / name,
        project / "doc" / name / "rules.md",
        project / "doc" / name / "needs.md",
        server / "tests/modules" / name,
        server / "tests/integration" / name,
    ]


# 把一个文件的内容计入摘要；路径和内容都参与，删除文件会少一条记录。
def _feed(digest: "hashlib._Hash", path: Path, project: Path, content: bytes) -> None:
    digest.update(path.relative_to(project).as_posix().encode() + b"\0")
    digest.update(content + b"\0")


# 公共部分的摘要：公共目录全部文件、非模块路由和登记文件的剩余公共部分。
# 读不出模块归属时，全部接口文件保守地算公共，登记文件按原始内容参与。
def _common_digest(project: Path, reader: Reader, owned: set[Path]) -> str:
    server = project / "server"
    files: set[Path] = set()
    for name in COMMON:
        files.update(reader.files_under(server / name, project))
    routes = set(reader.files_under(server / V1_FOLDER, project))
    files = (files - routes) | (routes - owned)
    files -= {server / relative for relative in REGISTRATIONS}
    digest = hashlib.sha256()
    for path in sorted(files):
        content = reader.read(path)
        if content is not None:
            _feed(digest, path, project, content)
    for relative, (names, prefixes) in sorted(REGISTRATIONS.items()):
        digest.update(relative.encode() + b"\0")
        digest.update(registration_entry(reader, server / relative, names, prefixes) + b"\0")
    return digest.hexdigest()


# 一个模块的版本 = 公共摘要 + 自身与全部声明依赖的业务文件、规则、测试和接口文件。
def _module_digest(
    project: Path,
    name: str,
    links: dict[str, dict[str, list[str]]],
    common: str,
    owned: dict[str, list[Path]],
    reader: Reader,
    registrations: dict[str, bytes],
) -> str:
    digest = hashlib.sha256()
    digest.update(b"common\0" + common.encode() + b"\0")
    files: set[Path] = set()
    for dependency in dependency_modules(name, links):
        digest.update(
            dependency.encode() + b"\0" + registrations.get(dependency, b"<missing>") + b"\0"
        )
        for path in module_paths(project, dependency):
            files.update(reader.files_under(path, project))
        files.update(owned.get(dependency, []))
    for path in sorted(files):
        content = reader.read(path)
        if content is not None:
            _feed(digest, path, project, content)
    return digest.hexdigest()


# 公共代码与全部声明依赖参与版本计算；没有依赖参数时保留独立模块用法。
# 公共文件一轮只读一次；总登记清单与模块自己的接口文件按归属参与对应模块的版本。
def fingerprints(
    project: Path, modules: list[str], links: dict[str, dict[str, list[str]]] | None = None
) -> dict[str, str]:
    reader = Reader()
    stems = route_ownership(reader.source(project / "server" / ROUTERS_FILE))
    owned = (
        {
            name: [project / "server" / V1_FOLDER / f"{stem}.py" for stem in names]
            for name, names in stems.items()
        }
        if stems is not None
        else {}
    )
    common = _common_digest(project, reader, {path for paths in owned.values() for path in paths})
    registrations = registration_parts(reader, project)
    return {
        name: _module_digest(project, name, links or {}, common, owned, reader, registrations)
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
                "source_changed": check["source_changed"],
                "fingerprints": check["fingerprints"],
            }
    return {"rounds": len(selected), "latest": latest}
