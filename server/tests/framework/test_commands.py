import asyncio
import json
import sys
from collections.abc import Callable
from decimal import Decimal
from functools import partial
from pathlib import Path

import fastapi_check.run_operation
import fastapi_operations.diagnose
import fastapi_operations.jobs
import fastapi_operations.make_key
import pytest
from sqlalchemy import update

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
    def __init__(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
        self.monkeypatch, self.capsys = monkeypatch, capsys

    def __call__(self, main: Callable[[], None], *args: str) -> str:
        self.capsys.readouterr()
        self.monkeypatch.setattr(sys, "argv", ["tool", *args])
        main()
        return self.capsys.readouterr().out


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = make_settings(tmp_path, run_records="database")
    reset_database_now(settings.database_url)
    monkeypatch.setenv("APP_DATABASE_URL", settings.database_url)
    monkeypatch.setenv("APP_RUN_RECORDS", "database")
    monkeypatch.setattr(fastapi_operations.diagnose, "application_modules", lambda: tuple(MODULES))
    monkeypatch.setattr(fastapi_operations.jobs, "application_modules", lambda: tuple(MODULES))
    return settings


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


async def set_state(url: str, job_id: str, state: str) -> None:
    database = Database(url)
    try:
        async with database.write() as connection:
            await connection.execute(update(jobs).where(jobs.c.id == job_id).values(state=state))
    finally:
        await database.close()


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


def test_run_operation_prints_result_and_report(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asyncio.run(prepare(settings))
    local = partial(build, modules=MODULES, provider=FakeModel())
    monkeypatch.setattr(fastapi_check.run_operation, "build", lambda settings: local(settings))

    def run_command(*args: str) -> tuple[int | str | None, str]:
        capsys.readouterr()
        monkeypatch.setattr(sys, "argv", ["dev run", *args])
        with pytest.raises(SystemExit) as stopped:
            fastapi_check.run_operation.main()
        return stopped.value.code, capsys.readouterr().out

    code, output = run_command("sample_calc.calc", "--allow-write", "--input", '{"amount": "8"}')
    assert code == 0 and "运行编号" in output and "成功" in output and "示例计算" in output
    code, output = run_command(
        "sample_calc.calc", "--allow-write", "--input", '{"amount": "8", "fail_at": "total"}'
    )
    assert code == 1 and "失败" in output and "运行编号" in output
    code, output = run_command("none.x")
    assert code == 1 and "没有登记操作" in output
