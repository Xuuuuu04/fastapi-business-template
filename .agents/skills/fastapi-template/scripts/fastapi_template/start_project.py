import argparse
import subprocess
import sys
from pathlib import Path

from fastapi_check.quality.rules import PROJECT
from fastapi_template.template.initialization import initialize


def main() -> None:
    parser = argparse.ArgumentParser(description="从模板开始干净的新产品项目")
    parser.add_argument("destination", type=Path, help="尚不存在的目标目录")
    parser.add_argument("--name", required=True, help="新产品名称")
    args = parser.parse_args()
    try:
        initialize(PROJECT, args.destination.absolute(), args.name)
    except ValueError as error:
        parser.error(str(error))
    result = subprocess.run(
        [sys.executable, "-m", "fastapi_dev.main", "docs"],
        cwd=args.destination / "server",
        check=False,
    )
    if result.returncode:
        parser.exit(1, "副本已创建，生成文档失败；请在副本安装依赖后重新生成并检查。\n")
    print(
        f"已创建：{args.destination.absolute()}。在 AGENTS.md 写业务要点，"
        "运行 uv sync 和 uv run dev check；数据库还没有创建。"
    )


if __name__ == "__main__":
    main()
