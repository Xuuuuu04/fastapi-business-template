import re
from pathlib import Path
from typing import Any


def case_current(case: dict[str, Any], suite: dict[str, Any], versions: dict[str, str]) -> bool:
    if not suite["current"]:
        return False
    recorded = suite["fingerprints"]
    owner = re.match(r"^tests/(?:modules|integration)/([^/]+)/", case["nodeid"])
    if owner is not None:
        name = owner.group(1)
        return name in versions and recorded.get(name) == versions[name]
    return bool(recorded) and all(versions.get(name) == code for name, code in recorded.items())


def check_scope(check: dict[str, Any]) -> dict[str, Any]:
    if "scope" in check:
        return check["scope"]
    if "默认测试" in check["checks"]:
        return {"kind": "all"}
    if "模块测试" in check["checks"]:
        return {"kind": "module"}
    return {"kind": "unknown"}


def latest_full_check(checks: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((check for check in reversed(checks) if check_scope(check)["kind"] == "all"), None)


def full_check_current(
    check: dict[str, Any], versions: dict[str, str], project: Path | None = None
) -> bool:
    modules_match = check["fingerprints"] == versions
    system_matches = project is None or check.get("system_fingerprint") == system_fingerprint(
        project
    )
    return not check["source_changed"] and modules_match and system_matches


def system_fingerprint(project: Path) -> str:
    from fastapi_project.development.history import COMMON, fingerprint

    server = project / "server"
    return fingerprint(
        [
            *[
                project / name.removeprefix("../") if name.startswith("../") else server / name
                for name in COMMON
            ],
            server / "app/setup/catalog.py",
            server / "app/api/routers.py",
            server / "tests/integration/system",
        ],
        project,
    )
