"""
只处理明确派生文件和有身份的JSON冲突，其他源码冲突保留给实际开发者处理。
"""

import re
from pathlib import Path

from fastapi_project.development.integration_documents import resolve_agents, resolve_index
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


# 可再生文件有固定范围，手写需求、规则和变化文档不会被通配覆盖。
def derived(name: str) -> bool:
    return name in DERIVED or bool(re.fullmatch(r"doc/[a-z][a-z0-9_]*/(?:flows|ledger)\.md", name))


# 三方提交原件先验证再写临时树，系统接口变化和普通源码冲突仍会停止。
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
        if derived(name):
            # 只在临时树取一份占位，后续docs必须重新生成并通过一致性检查。
            git(tree, "checkout", "--ours", "--", name)
            handled.append(name)
    for name in handled:
        git(tree, "add", "--", name)
