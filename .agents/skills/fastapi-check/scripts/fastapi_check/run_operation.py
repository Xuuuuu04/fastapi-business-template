import argparse
import asyncio
import sys
from dataclasses import replace
from pathlib import Path

from app.setup.application import application
from app.setup.build import build
from shared.access.caller import DEVELOPER
from shared.graphs.observed import run_report


async def run(name: str, text: str, org: str) -> int:
    services = build(application().settings())
    try:
        binding = services.catalog.find(name)
        if binding is None:
            print(f"没有登记操作 {name}，可用的操作：{'、'.join(sorted(services.catalog.by_name))}")
            return 1
        caller = replace(DEVELOPER, org_id=org)
        started: list[str] = []
        operation = binding.contract
        try:
            result = await services.runtime.run(
                operation,
                operation.input.model_validate_json(text),
                caller=caller,
                on_start=started.append,
            )
        except Exception as error:
            outcome, code = f"失败：{type(error).__name__} {error}", 1
        else:
            outcome, code = "成功\n" + result.model_dump_json(indent=2), 0
        await services.recorder.flush()
        print(f"运行编号 {started[0]}，{outcome}\n")
        print(run_report(await services.recorder.tree(started[0]), started[0]))
        return code
    finally:
        await services.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="用本地配置真跑一次操作，打印结果和运行报告")
    parser.add_argument("operation", help="操作名，例如 customer_contact.create_contact")
    parser.add_argument("--input", default="{}", help="输入 JSON")
    parser.add_argument("--input-file", type=Path, help="从文件读取输入 JSON")
    parser.add_argument("--org", default="*", help="以哪个组织的身份运行，默认全部组织")
    args = parser.parse_args()
    text = args.input_file.read_text(encoding="utf-8") if args.input_file else args.input
    sys.exit(asyncio.run(run(args.operation, text, args.org)))


if __name__ == "__main__":
    main()
