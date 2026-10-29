import subprocess
from pathlib import Path

from fastapi_project.development.integration_git import integrate


def run(project: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "user.name=synthetic-test", "-c", "user.email=test@example.invalid", *args],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def repository(path: Path) -> Path:
    path.mkdir()
    run(path, "init", "-b", "main")
    run(path, "config", "user.name", "synthetic-test")
    run(path, "config", "user.email", "test@example.invalid")
    (path / ".gitignore").write_text(".agents/records/\n")
    (path / "source.txt").write_text("old\n")
    run(path, "add", ".")
    run(path, "commit", "-m", "synthetic baseline")
    run(path, "switch", "-c", "feature")
    (path / "source.txt").write_text("incoming\n")
    run(path, "commit", "-am", "synthetic feature")
    run(path, "switch", "main")
    return path


def test_validated_candidate_applies_atomically(tmp_path: Path) -> None:
    project = repository(tmp_path / "repo")

    def validate(tree: Path) -> dict:
        assert (tree / "source.txt").read_text() == "incoming\n"
        assert (project / "source.txt").read_text() == "old\n"
        return {"passed": True, "kind": "synthetic-lifecycle-callback"}

    report = integrate(project, "feature", validate)
    assert report["applied"] and report["stage"] == "complete"
    assert (project / "source.txt").read_text() == "incoming\n"
    assert not run(project, "status", "--porcelain")
    assert not Path(report["tree"]).exists()


def test_failed_validation_preserves_original_branch(tmp_path: Path) -> None:
    project = repository(tmp_path / "repo")
    before = run(project, "rev-parse", "HEAD")
    report = integrate(project, "feature", lambda tree: {"passed": False})
    try:
        assert not report["applied"] and report["stage"] == "validate"
        assert run(project, "rev-parse", "HEAD") == before
        assert (project / "source.txt").read_text() == "old\n"
        assert not run(project, "status", "--porcelain")
        assert Path(report["tree"]).is_dir() and report["error"]
    finally:
        run(project, "worktree", "remove", "--force", report["tree"])


def test_source_conflict_stays_in_temporary_tree(tmp_path: Path) -> None:
    project = repository(tmp_path / "repo")
    (project / "source.txt").write_text("other change\n")
    run(project, "commit", "-am", "synthetic concurrent branch change")
    before = run(project, "rev-parse", "HEAD")
    report = integrate(project, "feature", lambda tree: {"passed": True})
    try:
        assert not report["applied"] and report["stage"] == "merge"
        assert "冲突" in report["error"]
        assert run(project, "rev-parse", "HEAD") == before
        assert not run(project, "status", "--porcelain")
    finally:
        run(project, "worktree", "remove", "--force", report["tree"])


def test_changed_original_refuses_candidate_apply(tmp_path: Path) -> None:
    project = repository(tmp_path / "repo")
    before = run(project, "rev-parse", "HEAD")

    def validate(tree: Path) -> dict:
        (project / "concurrent.txt").write_text("keep this change\n")
        return {"passed": True}

    report = integrate(project, "feature", validate)
    try:
        assert not report["applied"] and "变化" in report["error"]
        assert run(project, "rev-parse", "HEAD") == before
        assert (project / "concurrent.txt").read_text() == "keep this change\n"
    finally:
        run(project, "worktree", "remove", "--force", report["tree"])
