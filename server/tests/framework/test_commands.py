"""
命令行功能：按运行编号打印报告、人工处理后台任务，
fastapi_operations.make_key 生成服务密钥。命令从 APP_ 环境变量读取数据库地址，这里指向测试数据库，
模块清单换成测试用的示例模块，不依赖可以删除的业务模块。
"""

import asyncio
import json
import sys
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import fastapi_operations.diagnose
import fastapi_operations.jobs
import fastapi_operations.make_key
import pytest
from sqlalchemy import update

from app.setup.build import build
from deploy.check_env import check_configuration
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
from tests.framework.sample_resources import file_module, secret_module
from tests.testing_app import make_settings, reset_database_now

MODULES = [calc_module, outer_module]


# 测试命令行工具的输入与输出，避免真实终端交互。
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
    monkeypatch.setattr(fastapi_operations.diagnose, "application_modules", lambda: tuple(MODULES))
    monkeypatch.setattr(fastapi_operations.jobs, "application_modules", lambda: tuple(MODULES))
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


# 排查命令能列出运行、打印报告和统计，并说明操作的流程和字段来源。
def test_diagnose_commands(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run_id, _ = asyncio.run(prepare(settings))
    console, main = Console(monkeypatch, capsys), fastapi_operations.diagnose.main
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
    console, main = Console(monkeypatch, capsys), fastapi_operations.jobs.main
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
        fastapi_operations.make_key.main,
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


# 关闭需要加密的模块后不要求字段加密配置；文件服务按实际模块需求检查。
def test_deploy_checks_enabled_modules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.setup.build.MODULES", [file_module, secret_module])
    settings = make_settings(
        tmp_path,
        env="production",
        database_url="postgresql+psycopg://test:test@127.0.0.1/config-check-only",
        code_version="release-test",
        dev_caller=False,
        run_records="database",
        jwt_secret="independent-test-secret-with-32-characters",
        data_keys=[],
        disabled_modules=["sample_secrets"],
    )
    assert check_configuration(settings) == []
    settings.disabled_modules = []
    assert any("APP_DATA_KEYS" in problem for problem in check_configuration(settings))
    settings.disabled_modules = ["sample_secrets"]
    settings.file_storage = "s3"
    assert check_configuration(settings) == ["APP_FILE_STORAGE=s3 时必须配置 APP_S3_BUCKET"]
    settings.disabled_modules = ["sample_secrets", "sample_files"]
    assert check_configuration(settings) == []


# 关闭带提示词的模块后，部署检查不再要求大模型配置。
def test_deploy_ignores_disabled_model_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.setup.build.MODULES", MODULES)
    settings = make_settings(tmp_path)
    assert any("APP_MODEL_BASE_URL" in problem for problem in check_configuration(settings))
    settings.disabled_modules = [module.name for module in MODULES]
    assert check_configuration(settings) == []
