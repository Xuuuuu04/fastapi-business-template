import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi_check.quality.rules import ROOT


def test_dev_inspect_ignores_real_environment() -> None:
    environment = {**os.environ, "APP_ENV": "production", "APP_DATABASE_URL": "invalid-live"}
    result = subprocess.run(
        [sys.executable, "-c", "from fastapi_dev.main import main; main()", "inspect"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    description = json.loads(result.stdout)
    assert description["modules"] == [] and description["framework_version"] == "4.0.0"
    assert "invalid-live" not in result.stdout


def test_unknown_dev_command_fails_before_bootstrap(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", "from fastapi_dev.main import main; main()", "unknown-command"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2 and list(tmp_path.iterdir()) == []
