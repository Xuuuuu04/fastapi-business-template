import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi_project.development.history import save_check
from fastapi_project.development.panel_git import branch_status


def run(project: Path, *arguments: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=synthetic-test",
            "-c",
            "user.email=test@example.invalid",
            *arguments,
        ],
        cwd=project,
        check=True,
        capture_output=True,
    )


def evidence(project: Path, passed: bool) -> str:
    identity = uuid.uuid4().hex
    path = save_check(
        project,
        {
            "id": identity,
            "finished_at": datetime.now(UTC).isoformat(),
            "passed": passed,
            "source_changed": False,
            "fingerprints": {},
            "scope": {"kind": "all"},
            "checks": {},
            "suites": [],
        },
    )
    return path.stem


def test_branches_keep_worktree_evidence_separate(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    run(project, "init", "-b", "main")
    target = project / "server/service/sample_counts/calc/count.py"
    target.parent.mkdir(parents=True)
    target.write_text("value = 0\n")
    run(project, "add", ".")
    run(project, "commit", "-m", "synthetic baseline")
    trees = [tmp_path / "tree_a", tmp_path / "tree_b"]
    try:
        for number, tree in enumerate(trees, 1):
            run(project, "worktree", "add", "-b", f"fixture_{number}", str(tree), "main")
            (tree / target.relative_to(project)).write_text(f"value = {number}\n")
            run(tree, "add", ".")
            run(tree, "commit", "-m", "synthetic package change")
        identities = [evidence(tree, number == 0) for number, tree in enumerate(trees)]
        before = subprocess.check_output(["git", "status", "--porcelain"], cwd=project)
        status = branch_status(project)
        assert status["overlaps"] == [
            {"package": "sample_counts", "branches": ["fixture_1", "fixture_2"]}
        ]
        indexed = {tree["branch"]: tree for tree in status["worktrees"]}
        assert indexed["fixture_1"]["latest_check"]["id"] == identities[0]
        assert indexed["fixture_2"]["latest_check"]["id"] == identities[1]
        assert indexed["fixture_1"]["latest_check"]["passed"]
        assert not indexed["fixture_2"]["latest_check"]["passed"]
        assert subprocess.check_output(["git", "status", "--porcelain"], cwd=project) == before
    finally:
        for tree in trees:
            if tree.exists():
                run(project, "worktree", "remove", "--force", str(tree))
