import re
from pathlib import Path

from fastapi_project.development.integration_documents import (
    resolve_agents,
    resolve_index,
    resolve_ledger_section,
)
from fastapi_project.development.integration_git import git
from fastapi_project.development.integration_json import blob, resolve_json
from fastapi_project.development.integration_registry import regenerate_catalog, regenerate_routers

CATALOG = "server/app/setup/catalog.py"
ROUTERS = "server/app/api/routers.py"
DERIVED = {
    "doc/api/openapi.json",
    "doc/api/index.md",
    "doc/modules.md",
    "doc/progress.md",
    "doc/development.md",
}


def derived(name: str) -> bool:
    return name in DERIVED or bool(re.fullmatch(r"doc/[a-z][a-z0-9_]*/(?:flows|ledger)\.md", name))


def resolve(tree: Path, start: dict) -> None:
    ancestor = git(tree, "merge-base", start["head"], start["incoming"])
    commits = (ancestor, start["head"], start["incoming"])
    contents = {
        name: [blob(tree, commit, name) for commit in commits[1:]] for name in (CATALOG, ROUTERS)
    }
    if any(value is None for values in contents.values() for value in values):
        raise ValueError("整合缺少完整登记或路由原件")
    conflicts = git(tree, "diff", "--name-only", "--diff-filter=U").splitlines()
    regenerate_catalog(tree, [value.decode() for value in contents[CATALOG] if value is not None])
    regenerate_routers(tree, [value.decode() for value in contents[ROUTERS] if value is not None])
    json_files = resolve_json(tree, commits)
    handled = [CATALOG, ROUTERS, *json_files]
    index = resolve_index(tree, commits)
    if index:
        handled.append(index)
    agents = resolve_agents(tree, commits)
    if agents:
        handled.append(agents)
    for name in conflicts:
        if resolve_ledger_section(tree, commits, name):
            handled.append(name)
            continue
        if derived(name):
            git(tree, "checkout", "--ours", "--", name)
            handled.append(name)
    for name in handled:
        git(tree, "add", "--", name)
