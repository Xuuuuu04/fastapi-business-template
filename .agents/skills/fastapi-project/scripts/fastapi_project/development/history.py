import hashlib
from pathlib import Path
from typing import Any

from fastapi_project.development.check_index import read_records
from fastapi_project.development.check_storage import load_cases, save_record
from fastapi_project.development.ledger import read_ledger, scoped_digest
from fastapi_project.development.ledger_models import RuleLedger
from fastapi_project.development.versions import (
    EXCLUDED,
    REGISTRATIONS,
    ROUTERS_FILE,
    V1_FOLDER,
    Reader,
    registration_entry,
    registration_parts,
    route_ownership,
)

from shared.modules.libraries import library_closure, library_links, library_specs

COMMON = (
    "devtools",
    "../doc/glossary.json",
    "shared",
    "../.agents/skills",
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
    "tests/resources.py",
    "tests/postgres_setup.py",
    "tests/environment.py",
    "tests/check_profile.py",
    "pyproject.toml",
    "uv.lock",
    "migrations",
)


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


def dependency_modules(name: str, links: dict[str, dict[str, list[str]]]) -> list[str]:
    pending = [name]
    found: set[str] = set()
    while pending:
        module = pending.pop()
        if module not in found:
            found.add(module)
            pending.extend(links.get(module, {}))
    return sorted(found)


def module_paths(project: Path, name: str) -> list[Path]:
    server = project / "server"
    libraries = {spec.name for spec in library_specs(server)}
    closure = library_closure(name, library_links(server), libraries)
    return [
        server / "service" / name,
        project / "doc" / name / "rules.md",
        project / "doc" / name / "cases",
        project / "doc" / name / "needs.md",
        server / "tests/modules" / name,
        server / "tests/integration" / name,
        *[server / "library" / library for library in sorted(closure)],
    ]


def _feed(digest: "hashlib._Hash", path: Path, project: Path, content: bytes) -> None:
    digest.update(path.relative_to(project).as_posix().encode() + b"\0")
    digest.update(content + b"\0")


def _common_digest(project: Path, reader: Reader, owned: set[Path]) -> str:
    server = project / "server"
    files: set[Path] = set()
    for name in COMMON:
        path = project / name.removeprefix("../") if name.startswith("../") else server / name
        files.update(reader.files_under(path, project))
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


def _module_digest(
    project: Path,
    name: str,
    links: dict[str, dict[str, list[str]]],
    common: str,
    owned: dict[str, list[Path]],
    reader: Reader,
    registrations: dict[str, bytes],
    ledger: RuleLedger,
) -> str:
    digest = hashlib.sha256()
    digest.update(b"common\0" + common.encode() + b"\0")
    digest.update(
        b"rules\0" + scoped_digest(ledger, dependency_modules(name, links)).encode() + b"\0"
    )
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
    ledger = read_ledger(project)
    return {
        name: _module_digest(
            project, name, links or {}, common, owned, reader, registrations, ledger
        )
        for name in modules
    }


def save_check(project: Path, record: dict[str, Any]) -> Path:
    return save_record(project, record)


def read_checks(
    project: Path, extra: list[Path] | None = None, *, include_cases: bool = True
) -> list[dict[str, Any]]:
    return read_records(project, extra, include_cases)


def module_checks(checks: list[dict[str, Any]], module: str, current: str) -> dict[str, Any]:
    selected = [check for check in checks if module in check["fingerprints"]]
    latest: dict[str, Any] = {}
    sources: dict[str, dict[str, Any]] = {}
    for check in selected:
        for suite in check["suites"]:
            sources[suite["database"]] = suite
            latest[suite["database"]] = {
                **suite,
                "finished_at": check["finished_at"],
                "current": check["fingerprints"][module] == current and not check["source_changed"],
                "checks_passed": check["passed"],
                "source_changed": check["source_changed"],
                "fingerprints": check["fingerprints"],
            }
    for database, suite in latest.items():
        suite["cases"] = load_cases(sources[database])
    return {"rounds": len(selected), "latest": latest}
