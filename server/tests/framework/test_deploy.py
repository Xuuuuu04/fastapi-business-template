import subprocess
import sys
from pathlib import Path
from typing import Any

import fastapi_operations.deploy as deploy
import pytest


class Recorder:
    def __init__(self, failing: str = "") -> None:
        self.commands: list[list[str]] = []
        self.failing = failing

    def __call__(self, command: list[str], **options: Any) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        code = 1 if self.failing and self.failing in " ".join(command) else 0
        return subprocess.CompletedProcess(command, code, stdout="abc1234\n")


@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("DEPLOY_HOST=prod\nDEPLOY_DIR=/srv/app\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["dev deploy"])


@pytest.mark.usefixtures("server")
def test_push_update_and_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(subprocess, "run", recorder)
    deploy.main()
    push, update, ready = recorder.commands
    assert push == ["git", "push"]
    assert update[:2] == ["ssh", "prod"] and "cd /srv/app && git pull" in update[2]
    assert ready[:2] == ["ssh", "prod"] and "/health/ready" in ready[2]


@pytest.mark.usefixtures("server")
def test_stops_at_failed_step(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder(failing="git pull")
    monkeypatch.setattr(subprocess, "run", recorder)
    with pytest.raises(SystemExit, match="服务器拉取并重启失败"):
        deploy.main()
    assert len(recorder.commands) == 2


def test_requires_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEPLOY_HOST", raising=False)
    monkeypatch.delenv("DEPLOY_DIR", raising=False)
    with pytest.raises(SystemExit, match="DEPLOY_HOST"):
        deploy.target()
