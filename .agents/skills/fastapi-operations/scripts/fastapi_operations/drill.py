import argparse
import asyncio
import json
import tempfile
from dataclasses import replace
from pathlib import Path

from app.setup.catalog import MODULES
from app.setup.drill import execute
from shared.drills.isolation import isolated


async def run(args: argparse.Namespace) -> dict:
    modules = MODULES
    root = args.config.resolve().parent if args.config else Path.cwd()
    if args.sample:
        from shared.pipelines.plan import StartRequest
        from tests.framework.drill_sample import Begin, module, pipeline

        if args.scale < 1:
            raise ValueError("scale必须是正整数")
        schedule = replace(
            module.schedules[0],
            input=pipeline.start.input(request=StartRequest[Begin](data=Begin(count=args.scale))),
        )
        modules = [replace(module, schedules=(schedule,))]
    with tempfile.TemporaryDirectory(prefix="fastapi-drill-") as location:
        folder = Path(location)
        if args.sample:
            from tests.framework.test_pipeline_drill import original

            config = original(folder, args.scale)
            root = folder
        else:
            if args.config is None:
                raise ValueError("需要演练配置，或显式使用--sample")
            config = json.loads(args.config.read_text())
        async with isolated(folder, args.postgres) as url:
            return await execute(modules, config, url, folder, root, args.output.resolve())


def main() -> None:
    parser = argparse.ArgumentParser(description="按定时入口演练完整Pipeline并回放原件")
    parser.add_argument("config", type=Path, nargs="?")
    parser.add_argument("--sample", action="store_true")
    parser.add_argument("--scale", type=int, default=100000)
    parser.add_argument("--postgres", default="")
    parser.add_argument("--output", type=Path, default=Path("var/development/drill"))
    args = parser.parse_args()
    try:
        result = asyncio.run(run(args))
    except (ValueError, TimeoutError) as error:
        raise SystemExit(str(error)) from error
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("pipeline", "state", "needs_manual", "memory_peak_bytes", "coverage")
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print("演练报告：" + str(args.output.resolve() / "report.json"))
    if result["state"] != "succeeded" or result["needs_manual"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
