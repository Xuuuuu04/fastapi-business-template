"""
只读本地分支和工作树，按分支分别展示证据，不合并其他源码版本的结论。
"""

import json
import re
import subprocess
from pathlib import Path


# Git读命令失败保留说明，不操作分支、不拉取远程、不获取账号配置。
def git(project: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=project, capture_output=True, text=True, check=False, timeout=15
    )
    if result.returncode:
        raise ValueError("本地Git读取失败：" + " ".join(arguments[:2]))
    return result.stdout


# 工作树路径允许空格，分离HEAD明确标出；列表只包含当前仓库自己的工作树。
def worktrees(project: Path) -> list[dict]:
    entries = []
    for block in git(project, "worktree", "list", "--porcelain").strip().split("\n\n"):
        data = dict(line.partition(" ")[::2] for line in block.splitlines())
        if data.get("worktree"):
            entries.append(
                {
                    "path": data["worktree"],
                    "head": data.get("HEAD", ""),
                    "branch": data.get("branch", "detached").removeprefix("refs/heads/"),
                }
            )
    return entries


# 代码包与工具包按实际路径归属，框架改动另列，不把它们伪装成某个业务包。
def changed_packages(paths: list[str]) -> list[str]:
    return sorted(
        {
            match.group(1)
            for path in paths
            if (match := re.match(r"server/(?:service|library)/([^/]+)/", path))
        }
    )


# 其他工作树保留自己的最近记录，不加载其他项目的配置或生产数据库。
def tree_evidence(tree: dict) -> dict:
    path = Path(tree["path"])
    try:
        checks, warnings = tree_checks(path)
        latest = checks[-1] if checks else None
        evidence = (
            {
                key: latest.get(key)
                for key in (
                    "id",
                    "finished_at",
                    "passed",
                    "source_changed",
                    "scope",
                    "elapsed_seconds",
                )
            }
            if latest
            else None
        )
        dirty = git(path, "status", "--porcelain")
        return {
            **tree,
            "dirty": bool(dirty),
            "latest_check": evidence,
            "warning": "；".join(warnings),
            "meaning": "该工作树独立留存的历史记录；未加载其当前声明，不代表当前源码通过",
        }
    except (ValueError, OSError) as error:
        return {**tree, "latest_check": None, "warning": str(error)}


# 跨工作树不建立索引或转换历史原件，大旧记录明确提示在其自身工作树转换。
def tree_checks(project: Path) -> tuple[list[dict], list[str]]:
    checks, warnings = [], []
    for path in (project / "server/var/development/checks").glob("*.json"):
        if path.stat().st_size > 4 * 1024 * 1024:
            warnings.append(f"旧大记录{path.name}未展开，请在其自身工作树读取检查状态")
            continue
        value = json.loads(path.read_text())
        if not isinstance(value, dict) or not isinstance(value.get("finished_at"), str):
            raise ValueError("检查清单格式不完整：" + path.name)
        checks.append(value)
    return sorted(checks, key=lambda check: check["finished_at"]), warnings


# 分支重叠只提示同包同时有差异，实际冲突由临时整合检查确认。
def branch_status(project: Path) -> dict:
    try:
        trees = worktrees(project)
        names = git(project, "for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines()
        base = "main" if "main" in names else "HEAD"
        branches: list[dict] = []
        for name in names:
            paths = git(project, "diff", "--name-only", base + "..." + name, "--").splitlines()
            packages = changed_packages(paths)
            branches.append(
                {
                    "name": name,
                    "packages": packages,
                    "changed_files": len(paths),
                    "framework_changed": any(
                        path.startswith(("server/shared/", "server/app/", ".agents/skills/"))
                        for path in paths
                    ),
                }
            )
        overlaps = [
            {"package": package, "branches": users}
            for package in sorted(
                {package for branch in branches for package in branch["packages"]}
            )
            if len(
                users := [branch["name"] for branch in branches if package in branch["packages"]]
            )
            > 1
        ]
        return {
            "base": base,
            "branches": branches,
            "worktrees": [tree_evidence(tree) for tree in trees],
            "overlaps": overlaps,
            "warning": "",
        }
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        return {"branches": [], "worktrees": [], "overlaps": [], "warning": str(error)}
