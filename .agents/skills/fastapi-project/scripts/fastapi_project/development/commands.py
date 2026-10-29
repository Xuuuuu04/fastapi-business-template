import copy
import shlex
from collections.abc import Iterator
from pathlib import Path
from typing import Any


def module_links(module: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if "next" not in module:
        return
    yield module
    yield from (item for item in module.get("operations", []) if "next" in item)
    for suite in module["tests"]["latest"].values():
        yield from suite["problems"]


def generated_links(result: dict[str, Any]) -> Iterator[dict[str, Any]]:
    modules = list(result.get("modules", {}).values())
    if "tests" in result:
        modules.append(result)
    for module in modules:
        yield from module_links(module)
    for name in ("latest_check", "latest_full_check"):
        check = result.get(name)
        if check is not None:
            for suite in check["suites"].values():
                yield from suite["problems"]
    if "checks" in result:
        for suite in result["checks"]["latest"].values():
            yield from suite["problems"]
    if result.get("view") == "summary":
        for line in result.get("lines", []):
            yield from line["packages"]


def with_check_directories(result: dict[str, Any], directories: list[Path]) -> dict[str, Any]:
    if not directories:
        return result
    projected = copy.deepcopy(result)
    arguments = [argument for path in directories for argument in ("--checks", str(path.resolve()))]
    suffix = shlex.join(arguments)
    for entry in generated_links(projected):
        entry["next"] = f"{entry['next']} {suffix}"
    return projected
