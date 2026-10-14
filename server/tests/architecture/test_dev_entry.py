"""
已安装的短命令必须使用本产品目录，检查与生成仍走同一套工具。
"""

import ast
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from fastapi_check.quality.rules import ROOT

from tests.environment import subprocess_environment


# 子进程从实际已安装的开发包启动；部署环境不参与离线声明。
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
    assert description["modules"] == [] and description["framework_version"] == "3.1.1"
    assert "invalid-live" not in result.stdout


# 每个兼容长命令都有 dev 写法，说明和输出只需要用 dev；分步文档命令由 dev docs 一起执行。
def test_every_compat_command_has_dev_entry() -> None:
    from fastapi_dev.main import COMMANDS

    parts = {"fastapi_docs.api_doc", "fastapi_docs.flow_doc", "fastapi_docs.progress_doc"}
    missing = []
    for runner in sorted((ROOT.parent / ".agents/skills").glob("*/scripts/run_*.py")):
        package = "fastapi_" + runner.stem.removeprefix("run_")
        listed = next(
            node.value
            for node in ast.parse(runner.read_text(encoding="utf-8")).body
            if isinstance(node, ast.Assign) and ast.unparse(node.targets[0]) == "COMMANDS"
        )
        for command in ast.literal_eval(listed):
            target = f"{package}.{command}"
            if target not in COMMANDS.values() and target not in parts:
                missing.append(f"{runner.name} {command}")
    assert missing == []


# 未知命令不得开始生成，也不建立任何数据库连接。
def test_unknown_dev_command_fails_before_bootstrap(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", "from fastapi_dev.main import main; main()", "unknown-command"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2 and list(tmp_path.iterdir()) == []


# 只提供server内容的生产安装不能查找外部Skill元数据，也不能安装开发入口或pytest。
def test_server_only_locked_production_install(tmp_path: Path) -> None:
    target = tmp_path / "server"
    target.mkdir()
    for name in ("pyproject.toml", "uv.lock"):
        shutil.copy2(ROOT / name, target / name)
    shutil.copytree(
        ROOT / "devtools", target / "devtools", ignore=shutil.ignore_patterns("__pycache__")
    )
    env = subprocess_environment()
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        ["uv", "sync", "--python", sys.executable, "--locked", "--no-dev", "--offline"],
        cwd=target,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr[-1500:]
    script = (
        "import importlib.util; import fastapi; "
        "assert importlib.util.find_spec('fastapi_dev') is None; "
        "assert importlib.util.find_spec('pytest') is None"
    )
    checked = subprocess.run(
        [str(target / ".venv/bin/python"), "-c", script],
        cwd=target,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert checked.returncode == 0, checked.stderr


# 开发入口源码变化必须让完整证据过期，生产启动范围则允许不携带开发工具。
def test_development_source_is_fingerprinted(tmp_path: Path) -> None:
    from fastapi_project.development.evidence import system_fingerprint

    from shared.modules.validation.framework_lock import differences, digests

    folder = tmp_path / "server/devtools/src/fastapi_dev"
    folder.mkdir(parents=True)
    code = folder / "main.py"
    code.write_text("value = 1\n")
    first = system_fingerprint(tmp_path)
    code.write_text("value = 2\n")
    assert system_fingerprint(tmp_path) != first
    lock = tmp_path / "server/framework.lock"
    lock.write_text(json.dumps(digests(tmp_path / "server")))
    shutil.rmtree(tmp_path / "server/devtools")
    assert differences(tmp_path / "server", include_skills=False) == []
    assert any("devtools" in problem for problem in differences(tmp_path / "server"))
