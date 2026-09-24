"""
命令行工具：tools.diagnose 按运行编号打印中文诊断报告，tools.jobs 人工处理后台任务，
tools.make_key 生成服务密钥。命令从 APP_ 环境变量读取数据库地址，这里指向测试数据库，
模块清单换成测试用的示例模块，不依赖可以删除的业务模块。
"""

import asyncio
import json
import sys
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import update

import tools.diagnose
import tools.jobs
import tools.make_key
from app.setup.build import build
from shared.access.caller import DEVELOPER
from shared.access.keys import hash_key
from shared.config.settings import Settings
from shared.db.database import Database
from shared.jobs.tables import jobs
from shared.model_calls.providers import FakeModel
from tests.framework.sample_modules import (
    CalcInput,
    calc,
    calc_module,
    outer_module,
    sample_metadata,
)
from tests.testing_app import make_settings, reset_database_now

MODULES = [calc_module, outer_module]


class Console:
    # 用给定的参数执行命令行入口，返回打印的内容。
    def __init__(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
        self.monkeypatch, self.capsys = monkeypatch, capsys

    # 执行一条命令。
    def __call__(self, main: Callable[[], None], *args: str) -> str:
        self.capsys.readouterr()
        self.monkeypatch.setattr(sys, "argv", ["tool", *args])
        main()
        return self.capsys.readouterr().out


# 准备测试数据库，并让命令行工具连接它、使用示例模块。
@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = make_settings(tmp_path, run_records="database")
    reset_database_now(settings.database_url)
    monkeypatch.setenv("APP_DATABASE_URL", settings.database_url)
    monkeypatch.setenv("APP_RUN_RECORDS", "database")
    monkeypatch.setattr(tools.diagnose, "MODULES", MODULES)
    monkeypatch.setattr(tools.jobs, "MODULES", MODULES)
    return settings


# 执行一次计算并登记一个任务，返回运行编号和任务编号。
async def prepare(settings: Settings) -> tuple[str, str]:
    services = build(settings, modules=MODULES, provider=FakeModel())
    try:
        async with services.database.write() as connection:
            await connection.run_sync(sample_metadata.drop_all)
            await connection.run_sync(sample_metadata.create_all)
        run_ids: list[str] = []
        await services.runtime.run(
            calc, CalcInput(amount=Decimal("8")), caller=DEVELOPER, on_start=run_ids.append
        )
        job_id = await services.runtime.submit(
            calc, CalcInput(amount=Decimal("2")), caller=DEVELOPER
        )
        return run_ids[0], job_id
    finally:
        await services.close()


# 直接修改任务状态，模拟任务失败或等待兼容版本。
async def set_state(url: str, job_id: str, state: str) -> None:
    database = Database(url)
    try:
        async with database.write() as connection:
            await connection.execute(update(jobs).where(jobs.c.id == job_id).values(state=state))
    finally:
        await database.close()


# 诊断命令能列出运行、打印报告和统计，并说明操作的流程和字段来源。
def test_diagnose_commands(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run_id, _ = asyncio.run(prepare(settings))
    console, main = Console(monkeypatch, capsys), tools.diagnose.main
    assert run_id in console(main, "runs")
    report = console(main, "run", run_id)
    assert run_id in report and "计算" in report
    assert "没有找到运行" in console(main, "run", "0000000000000000")
    assert "sample_calc.calc" in console(main, "stats")
    assert "```mermaid" in console(main, "flow", "sample_calc.calc")
    assert "没有登记操作" in console(main, "flow", "none.x")
    assert "应付" in console(main, "field", "sample_calc.calc", "total")


# 任务命令：修改状态必须加 --yes；取消、重新排队、确认版本后重新排队按状态给出结果。
def test_job_commands(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _, job_id = asyncio.run(prepare(settings))
    console, main = Console(monkeypatch, capsys), tools.jobs.main
    assert job_id in console(main, "list")
    assert job_id in console(main, "show", job_id)
    assert "需要加 --yes" in console(main, "cancel", job_id)
    assert console(main, "cancel", job_id, "--yes").strip() == "已取消"
    assert "只能取消" in console(main, "cancel", job_id, "--yes")
    asyncio.run(set_state(settings.database_url, job_id, "failed"))
    assert console(main, "requeue", job_id, "--yes").strip() == "已重新排队"
    assert "任务状态是" in console(main, "requeue", job_id, "--yes")
    asyncio.run(set_state(settings.database_url, job_id, "blocked"))
    assert "--accept-version" in console(main, "requeue", job_id, "--yes")
    accepted = console(main, "requeue", job_id, "--yes", "--accept-version")
    assert accepted.strip() == "已重新排队"
    assert "任务不存在" in console(main, "requeue", "missing", "--yes")


# 生成的密钥原文与配置中的摘要对应，组织和权限按参数写入。
def test_make_key(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    printed = Console(monkeypatch, capsys)(
        tools.make_key.main,
        "--name",
        "reporting",
        "--permissions",
        "sample_calc.use",
        "--org-id",
        "north",
    )
    lines = printed.splitlines()
    config = json.loads(lines[-1])
    assert config["key_sha256"] == hash_key(lines[1])
    assert (config["org_id"], config["permissions"]) == ("north", ["sample_calc.use"])
