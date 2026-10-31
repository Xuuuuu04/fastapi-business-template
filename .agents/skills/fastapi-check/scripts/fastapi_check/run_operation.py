import asyncio
import sys
from dataclasses import replace
from typing import Any

from fastapi_check.run_cases import RunCase, arguments
from pydantic import ValidationError

from app.setup.application import application
from app.setup.build import Services, build
from shared.access.caller import DEVELOPER
from shared.graphs.observed import run_report
from shared.modules.contract import Contract


async def run(case: RunCase, allow_write: bool) -> int:
    settings = application().settings()
    if settings.env == "production":
        print("dev run 只用于本地或测试环境；生产排查请使用 dev diagnose")
        return 1
    services = build(settings)
    try:
        binding = services.catalog.find(case.operation)
        if binding is None:
            print(f"没有登记操作 {case.operation}，请用 dev locate 查找")
            return 1
        if binding.contract.effect == "command" and not allow_write:
            print("该操作可能写入；确认本地配置和样例后加 --allow-write")
            return 1
        return await execute_case(services, binding.contract, case)
    finally:
        await services.close()


async def execute_case(services: Services, operation: Contract[Any, Any], case: RunCase) -> int:
    caller = replace(DEVELOPER, org_id=case.org, permissions=frozenset(case.permissions))
    started: list[str] = []
    try:
        input = operation.input.model_validate(case.input)
    except ValidationError as error:
        fields = [".".join(map(str, issue["loc"])) for issue in error.errors()]
        print(f"输入不符合操作要求，字段：{'、'.join(fields)}；操作尚未执行")
        return 1
    try:
        result = await services.runtime.run(
            operation, input, caller=caller, on_start=started.append
        )
    except Exception as error:
        outcome, code = f"失败：{type(error).__name__}", 1
    else:
        outcome, code = "成功\n" + result.model_dump_json(indent=2), 0
        if case.expected is not None and result.model_dump(mode="json") != case.expected:
            outcome, code = (
                "业务样例结果不符合 expected，实际结果：\n" + result.model_dump_json(indent=2),
                1,
            )
    await services.recorder.flush()
    if not started:
        print(outcome + "（操作未启动）")
        return code
    print(f"运行编号 {started[0]}，{outcome}\n")
    print(run_report(await services.recorder.tree(started[0]), started[0]))
    return code


def main() -> None:
    case, allow_write = arguments()
    sys.exit(asyncio.run(run(case, allow_write)))


if __name__ == "__main__":
    main()
