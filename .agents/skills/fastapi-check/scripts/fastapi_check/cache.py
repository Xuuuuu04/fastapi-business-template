import hashlib
import json
import platform
from importlib.metadata import version
from pathlib import Path
from typing import Any

from fastapi_check.matrix import CheckOptions, clean_environment, databases
from fastapi_project.development.history import read_checks


def execution_profile(options: CheckOptions, postgres: str) -> dict[str, Any]:
    services = {
        key: value for key, value in clean_environment().items() if key.startswith("APP_TEST_")
    }
    services["postgres"] = postgres
    return {
        "group": options.group,
        "workers": options.workers,
        "databases": list(databases(postgres, options.database)),
        "python": platform.python_version(),
        "platform": platform.system(),
        "pytest": version("pytest"),
        "sqlalchemy": version("sqlalchemy"),
        "test_services": hashlib.sha256(json.dumps(services, sort_keys=True).encode()).hexdigest(),
    }


def cached_round(
    project: Path,
    fingerprints: dict[str, str],
    system: str,
    scope: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any] | None:
    checks = read_checks(project, include_cases=False)
    for check in reversed(checks):
        if check.get("scope") != scope or check.get("execution_profile") != profile:
            continue
        if check.get("source_changed") or check.get("fingerprints") != fingerprints:
            return None
        if check.get("system_fingerprint") != system or not check.get("passed"):
            return None
        if any(
            not (Path(suite["_artifact_root"]) / suite["case_file"]).is_file()
            for suite in check.get("suites", [])
            if suite.get("case_file")
        ):
            return None
        return check
    return None
