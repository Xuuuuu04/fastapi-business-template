"""
项目 Skill 的产品复制、旧工具升级与部署独立性。
检查实际文件与子进程，不把说明文件存在当成脚本可用。
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from fastapi_check.quality.rules import PROJECT
from fastapi_template.template.files import save_provenance
from fastapi_template.template.initialization import initialize
from fastapi_template.template.merge import apply_plan, update_plan

from shared.modules.validation.framework_lock import differences


# 只复制项目 Skill，不复制本机任务；副本命令必须读取副本产品，而非原模板。
def test_copy_retains_skills_and_uses_product_paths(tmp_path: Path) -> None:
    target = tmp_path / "product"
    initialize(PROJECT, target, "独立产品")
    assert sorted(path.name for path in (target / ".agents").iterdir()) == ["skills"]
    command = target / ".agents/skills/fastapi-project/scripts/run_project.py"
    result = subprocess.run(
        [sys.executable, str(command), "project", "--summary", "--json"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    status = json.loads(result.stdout)
    assert status["name"] == "独立产品" and status["check_rounds"] == 0


# 旧模板的 tools 文件按原来源参与比较，更新后删除它并加入新的项目 Skill。
def test_upgrade_removes_old_tools_and_copies_skills(tmp_path: Path) -> None:
    base, source, target = [tmp_path / name for name in ("old", "new", "product")]
    for project in (base, source, target):
        (project / "server").mkdir(parents=True)
        (project / "server/pyproject.toml").write_text('[project]\nversion = "2.0.0"\n')
    for project in (base, target):
        (project / "server/tools").mkdir()
        (project / "server/tools/check.py").write_text("VERSION = 1\n")
    skill = ".agents/skills/fastapi-check/scripts/run_check.py"
    (source / skill).parent.mkdir(parents=True)
    (source / skill).write_text("VERSION = 2\n")
    save_provenance(target, base)
    changes, _ = update_plan(target, base, source)
    assert any(item.name == "server/tools/check.py" and item.state == "delete" for item in changes)
    apply_plan(target, base, source, changes)
    assert not (target / "server/tools/check.py").exists()
    assert (target / skill).read_text() == "VERSION = 2\n"


# 部署只复制 server/；服务启动检查不依赖 Agent Skill，也不忽略公共源码变化。
def test_server_starts_without_project_skills(tmp_path: Path) -> None:
    target = tmp_path / "product"
    initialize(PROJECT, target, "部署样例")
    shutil.rmtree(target / ".agents")
    result = subprocess.run(
        [sys.executable, "-c", "from app.setup.web import create_app; create_app()"],
        cwd=target / "server",
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    file = target / "server/shared/modules/layout.py"
    file.write_text(file.read_text() + "\nCHANGED = True\n")
    assert any("layout.py" in name for name in differences(target / "server", include_skills=False))
