"""
整合只在临时工作树中修改源码，原分支在验证成功且基线未变化时才快进。
"""

import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi_project.development.check_assets import atomic_bytes


# 只执行明确Git参数，不拼接shell；失败信息不包含工作区凭据或环境。
def git(project: Path, *arguments: str, accepted: tuple[int, ...] = (0,)) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=project, capture_output=True, text=True, check=False, timeout=30
    )
    if result.returncode not in accepted:
        raise ValueError("Git步骤失败：" + " ".join(arguments[:2]))
    return result.stdout.strip()


# 所有原件必须干净且在命名分支，临时整合不替用户处理尚未提交的其他工作。
def baseline(project: Path, branch: str) -> dict:
    if not branch or branch.startswith("-") or "\0" in branch:
        raise ValueError("分支参数不合法")
    if git(project, "status", "--porcelain"):
        raise ValueError("原工作区有未提交改动，请先保存后再整合")
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", ".agents/records/integrations/"],
        cwd=project,
        check=False,
    )
    if ignored.returncode:
        raise ValueError("本机整合资料目录必须先加入Git忽略范围")
    name = git(project, "symbolic-ref", "--quiet", "HEAD")
    return {
        "head": git(project, "rev-parse", "HEAD"),
        "branch": name,
        "incoming": git(project, "rev-parse", "--verify", branch + "^{commit}"),
    }


# 工作树处于detached状态，任何冲突和修复不会在原分支留下半次合并。
def prepare(project: Path, start: dict) -> tuple[str, Path]:
    identity = uuid.uuid4().hex
    tree = project / ".agents/records/integrations" / identity / "tree"
    tree.parent.mkdir(parents=True)
    git(project, "worktree", "add", "--detach", str(tree), start["head"])
    return identity, tree


# 原分支和提交、工作区再次一起核对，其他人开发期间的变化不能被本次整合覆盖。
def unchanged(project: Path, start: dict) -> None:
    if (
        git(project, "rev-parse", "HEAD") != start["head"]
        or git(project, "symbolic-ref", "--quiet", "HEAD") != start["branch"]
        or git(project, "status", "--porcelain")
    ):
        raise ValueError("原分支在检查期间变化，请重新整合")


# 源码在临时树验证后提交，只有本次合并结果被应用，不能隐含执行远程发布。
def integrate(
    project: Path,
    branch: str,
    validate: Callable[[Path], dict],
    resolve: Callable[[Path, dict], None] | None = None,
    *,
    preview: bool = False,
) -> dict:
    start = baseline(project, branch)
    identity, tree = prepare(project, start)
    report: dict[str, Any] = {
        "id": identity,
        "base": start,
        "tree": str(tree),
        "stage": "merge",
        "applied": False,
    }
    try:
        git(tree, "merge", "--no-commit", "--no-ff", start["incoming"], accepted=(0, 1))
        if resolve:
            resolve(tree, start)
        conflicts = git(tree, "diff", "--name-only", "--diff-filter=U").splitlines()
        if conflicts:
            raise ValueError("源码冲突尚未处理：" + ",".join(conflicts))
        report["stage"] = "validate"
        evidence = validate(tree)
        report["evidence"] = evidence
        if not evidence.get("passed"):
            report["stage"] = evidence.get("stage", "validate")
            raise ValueError("临时整合检查没有通过")
        git(tree, "add", "-A")
        if (
            git(tree, "status", "--porcelain")
            or (tree / ".git").is_file()
            and git(tree, "rev-parse", "--verify", "MERGE_HEAD", accepted=(0, 128))
        ):
            git(tree, "commit", "-m", "Integrate branch after local validation")
        report["candidate"] = git(tree, "rev-parse", "HEAD")
        report["stage"] = "ready"
        if not preview:
            unchanged(project, start)
            git(project, "merge", "--ff-only", report["candidate"])
            report["applied"] = True
            report["stage"] = "complete"
            git(project, "worktree", "remove", "--force", str(tree))
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        report["error"] = str(error)
    save_report(project, report)
    return report


# 失败和预览保留可复核工作树，报告留在忽略目录，不把“计划通过”当作完成。
def save_report(project: Path, report: dict) -> Path:
    import json

    path = project / ".agents/records/integrations" / report["id"] / "report.json"
    atomic_bytes(path, (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode())
    return path
