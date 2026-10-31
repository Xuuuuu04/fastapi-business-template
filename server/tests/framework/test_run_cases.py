import json
import sys

import pytest
from fastapi_check import run_operation
from fastapi_check.run_cases import RunCase, arguments

from app.setup.build import Services


@pytest.mark.parametrize(
    "args",
    [
        ["sample_calc.calc", "--input", "{"],
        ["sample_calc.calc", "--input", ""],
        ["--case", "missing.json"],
    ],
)
def test_invalid_case_reports_usage(monkeypatch: pytest.MonkeyPatch, args: list[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["dev run", *args])
    with pytest.raises(SystemExit) as caught:
        arguments()
    assert caught.value.code == 2


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("body", "allow_write", "message"),
    [({}, True, "操作尚未执行"), ({"amount": "1"}, False, "--allow-write")],
)
async def test_run_rejects_before_execution(
    sample: Services,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    body: dict,
    allow_write: bool,
    message: str,
) -> None:
    monkeypatch.setattr(run_operation, "build", lambda settings: sample)
    code = await run_operation.run(RunCase(operation="sample_calc.calc", input=body), allow_write)
    assert code == 1 and message in capsys.readouterr().out
    assert sample.recorder.state().active == 0


@pytest.mark.anyio
async def test_case_checks_expected_output(
    sample: Services, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(run_operation, "build", lambda settings: sample)
    case = RunCase.model_validate_json(
        json.dumps(
            {
                "operation": "sample_calc.calc",
                "input": {"amount": "2"},
                "permissions": ["sample_calc.use"],
                "org": "test",
                "expected": {"total": "999", "saved": 1},
            }
        )
    )
    assert await run_operation.run(case, True) == 1
    assert "不符合 expected" in capsys.readouterr().out


@pytest.mark.anyio
async def test_run_rejects_production_before_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")

    def unexpected(settings: object) -> None:
        pytest.fail("生产环境不应建立运行服务")

    monkeypatch.setattr(run_operation, "build", unexpected)
    assert await run_operation.run(RunCase(operation="sample_calc.calc"), True) == 1
