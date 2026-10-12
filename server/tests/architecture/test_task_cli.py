"""
实际生成项目的start/finish验收，模拟拒绝、当前双库成功和确认预期修改分别留真实证据。
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi_check.quality.rules import PROJECT
from fastapi_template.template.initialization import initialize

from tests.architecture.test_operation_generators import COPY_FLAG, run
from tests.environment import subprocess_environment
from tests.framework.skeleton_sample import implement, write_inputs


# finish有检查过程输出，最后一份JSON才是收工结论。
def conclusion(text: str) -> dict:
    return json.loads(text[text.rfind("\n{") + 1 :])


# 隔离PostgreSQL凭据只在子进程内读取，不放在命令参数、断言或检查资料里。
PRIVATE_FINISH = """
import json, subprocess, sys
from urllib.parse import quote
from fastapi_dev.main import bootstrap, project_root
root = project_root(); bootstrap(root)
from fastapi_dev.tasks import finish
from app.setup.application import application_modules
from shared.modules.catalog import Catalog
container = json.loads(subprocess.check_output(['docker', 'inspect', 'gen3-template-postgres']))[0]
assert container['Config']['Labels'].get('codex.goal') == 'gen3-template-v3'
values = dict(item.split('=', 1) for item in container['Config']['Env'] if '=' in item)
url = ('postgresql+psycopg://' + quote(values.get('POSTGRES_USER', 'postgres'), safe='')
       + ':' + quote(values['POSTGRES_PASSWORD'], safe='')
       + '@127.0.0.1:15471/template_control')
result = finish(root, Catalog(application_modules()), sys.argv[1], url)
print(json.dumps(result, ensure_ascii=False, indent=2))
"""


# 在真实开发命令里走模拟、确认、开工和双库收工，不伪造检查记录。
@pytest.mark.sqlite_template
def test_real_task_commands_use_fresh_database_evidence(tmp_path: Path) -> None:
    if os.environ.get(COPY_FLAG):
        pytest.skip("模板副本不递归执行任务验收")
    copy = tmp_path / "product"
    initialize(PROJECT, copy, "任务命令验收")
    spec = write_inputs(copy)
    env = subprocess_environment() | {COPY_FLAG: "1"}
    entry = ["-c", "from fastapi_dev.main import main; main()"]
    run(copy, [*entry, "skeleton", "--spec", str(spec)], env)
    first = json.loads(
        run(copy, [*entry, "start", "--package", "sample_counts", "--cases", "R-01-C01"], env)
    )
    refused = subprocess.run(
        [sys.executable, *entry, "finish", "--task", first["id"]],
        cwd=copy / "server",
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert refused.returncode == 1 and conclusion(refused.stdout)["state"] == "incomplete"
    assert "模拟骨架" in refused.stdout
    implement(copy)
    run(copy, ["-m", "ruff", "check", "service", "--fix"], env)
    run(copy, ["-m", "ruff", "format", "service"], env)
    rule_commands(copy, entry, env)
    run(copy, [*entry, "docs"], env)
    card = json.loads(
        run(copy, [*entry, "start", "--package", "sample_counts", "--cases", "R-01-C01"], env)
    )
    output = run(copy, ["-c", PRIVATE_FINISH, card["id"]], env)
    result = conclusion(output)
    assert result["state"] == "complete" and result["checks"]
    record = json.loads(
        (copy / "server/var/development/checks" / (result["checks"][-1] + ".json")).read_text()
    )
    assert record["passed"] and not record["source_changed"]
    assert {suite["database"] for suite in record["suites"]} == {"sqlite", "postgresql"}
    reject_modified_expectation(copy, entry, env)


# 改独立预期后局部交付检查也必须失败，而不是只靠整项目检查发现。
def reject_modified_expectation(copy: Path, entry: list[str], env: dict[str, str]) -> None:
    fixture = copy / "doc/sample_counts/cases/one.json"
    data = json.loads(fixture.read_text())
    data["expected"]["value"] += 1
    fixture.write_text(json.dumps(data))
    rejected = subprocess.run(
        [sys.executable, *entry, "check", "--module", "sample_counts", "--delivery"],
        cwd=copy / "server",
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert rejected.returncode != 0 and "确认输入、预期或关键断言已经改变" in rejected.stdout


# 全部是虚构原话与虚构确认声明，仅检验工具路径，不代表人类业务确认。
def rule_commands(copy: Path, entry: list[str], env: dict[str, str]) -> None:
    source = [
        "rules",
        "source",
        "synthetic-source",
        "--kind",
        "user_quote",
        "--summary",
        "虚构确认原话，仅工具测试",
        "--locator",
        "fixture:synthetic",
    ]
    proposed = [
        "rules",
        "propose",
        "sample_counts.R-01",
        "--text",
        "合成数量加一",
        "--source",
        "synthetic-source",
        "--risk",
        "low",
        "--reason",
        "独立合成预期",
    ]
    adopted = ["rules", "adopt", "sample_counts.R-01", "--reason", "虚构采纳声明"]
    confirmed = [
        "rules",
        "confirm",
        "sample_counts.R-01",
        "--source",
        "synthetic-source",
        "--revision",
        "1",
        "--kind",
        "human_explicit",
        "--note",
        "虚构确认声明，仅验工具，不是人类业务确认",
        "--recorded-by",
        "synthetic-test",
    ]
    for arguments in (source, proposed, adopted, confirmed):
        run(copy, [*entry, *arguments], env)
