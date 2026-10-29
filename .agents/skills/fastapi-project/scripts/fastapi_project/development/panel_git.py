import json
import re
import subprocess
from pathlib import Path


def git(project: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=project, capture_output=True, text=True, check=False, timeout=15
    )
    if result.returncode:
        raise ValueError("本地Git读取失败：" + " ".join(arguments[:2]))
    return result.stdout


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


def changed_packages(paths: list[str]) -> list[str]:
    return sorted(
        {
            match.group(1)
            for path in paths
            if (match := re.match(r"server/(?:service|library)/([^/]+)/", path))
        }
    )


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
