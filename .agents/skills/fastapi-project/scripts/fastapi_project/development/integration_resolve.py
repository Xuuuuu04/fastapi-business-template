import subprocess
from pathlib import Path

from fastapi_project.development.integration_git import git
from fastapi_project.development.integration_registry import regenerate_catalog, regenerate_routers

CATALOG = "server/app/setup/catalog.py"
ROUTERS = "server/app/api/routers.py"
DERIVED = {"doc/api/openapi.json"}


def blob(project: Path, commit: str, name: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", commit + ":" + name],
        cwd=project,
        capture_output=True,
        check=False,
        timeout=15,
    )
    if result.returncode == 128:
        return None
    if result.returncode:
        raise ValueError("不能读取整合原件：" + name)
    return result.stdout


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
    handled = [CATALOG, ROUTERS]
    for name in conflicts:
        if name in DERIVED:
            git(tree, "checkout", "--ours", "--", name)
            handled.append(name)
    for name in handled:
        git(tree, "add", "--", name)
