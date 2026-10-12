"""
真实临时Git仓库验证整合生命周期，验证器在这里为边界回调，不冒充框架双库检查。
"""

import subprocess
from pathlib import Path

from fastapi_project.development.integration_git import integrate


# 提交身份仅写入临时仓库命令，不修改用户Git配置。
def run(project: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "user.name=synthetic-test", "-c", "user.email=test@example.invalid", *args],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


# 独立仓库有命名分支和忽略目录，源码不包含环境或产品资料。
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


# 成功应用只快进已验证候选，临时工作树清理，原工作区保持干净。
def test_validated_candidate_applies_atomically(tmp_path: Path) -> None:
    project = repository(tmp_path / "repo")

    # 生命周期回调只证明候选源码被验证器看到，真实框架验证另有集成测试。
    def validate(tree: Path) -> dict:
        assert (tree / "source.txt").read_text() == "incoming\n"
        assert (project / "source.txt").read_text() == "old\n"
        return {"passed": True, "kind": "synthetic-lifecycle-callback"}

    report = integrate(project, "feature", validate)
    assert report["applied"] and report["stage"] == "complete"
    assert (project / "source.txt").read_text() == "incoming\n"
    assert not run(project, "status", "--porcelain")
    assert not Path(report["tree"]).exists()


# 失败保留工作树和报告，原提交、分支和源码均不改变。
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


# 真实文本冲突在验证前停止，不隐含选择ours/theirs。
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


# 外部改动发生在验证期间时，不能覆盖它或错误报告已经应用。
def test_changed_original_refuses_candidate_apply(tmp_path: Path) -> None:
    project = repository(tmp_path / "repo")
    before = run(project, "rev-parse", "HEAD")

    # 模拟另一开发者在原工作区新增文件，候选已经验证也不能忽略该变化。
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
