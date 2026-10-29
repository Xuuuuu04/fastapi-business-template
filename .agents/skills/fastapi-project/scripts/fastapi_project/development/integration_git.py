import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi_project.development.check_assets import atomic_bytes


def git(project: Path, *arguments: str, accepted: tuple[int, ...] = (0,)) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=project, capture_output=True, text=True, check=False, timeout=30
    )
    if result.returncode not in accepted:
        raise ValueError("Git步骤失败：" + " ".join(arguments[:2]))
    return result.stdout.strip()


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


def prepare(project: Path, start: dict) -> tuple[str, Path]:
    identity = uuid.uuid4().hex
    tree = project / ".agents/records/integrations" / identity / "tree"
    tree.parent.mkdir(parents=True)
    git(project, "worktree", "add", "--detach", str(tree), start["head"])
    return identity, tree


def unchanged(project: Path, start: dict) -> None:
    if (
        git(project, "rev-parse", "HEAD") != start["head"]
        or git(project, "symbolic-ref", "--quiet", "HEAD") != start["branch"]
        or git(project, "status", "--porcelain")
    ):
        raise ValueError("原分支在检查期间变化，请重新整合")


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


def save_report(project: Path, report: dict) -> Path:
    import json

    path = project / ".agents/records/integrations" / report["id"] / "report.json"
    atomic_bytes(path, (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode())
    return path
