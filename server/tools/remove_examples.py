"""
用模板开始新项目时，删除两个示例模块（商品目录、订单报价）：
模块代码、接口、测试、业务文档、登记，以及包含示例表的迁移；然后重新生成只含框架表的初始迁移和文档。
只用于还没有真实数据的新项目。用法：uv run python -m tools.remove_examples --yes
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from tools.quality.rules import PROJECT, ROOT

EXAMPLES = ("product_catalog", "order_quote")


# 列出要删除的示例文件和目录。
def example_paths() -> list[Path]:
    paths = []
    for name in EXAMPLES:
        paths += [ROOT / "service" / name, ROOT / "app" / "api" / "v1" / f"{name}.py"]
        paths += [ROOT / "tests" / "modules" / name, ROOT / "tests" / "integration" / name]
        paths.append(PROJECT / "doc" / name)
    paths += sorted((ROOT / "migrations" / "versions").glob("*.py"))
    return [path for path in paths if path.exists()]


# 从登记文件和业务文档目录中去掉示例。
def unregister() -> None:
    catalog = ROOT / "app" / "setup" / "catalog.py"
    text = catalog.read_text(encoding="utf-8")
    for name in EXAMPLES:
        text = re.sub(rf"from service\.{name}\.module import module as {name}\n", "", text)
        text = re.sub(rf"\n    {name},", "", text)
    catalog.write_text(text, encoding="utf-8")
    routers = ROOT / "app" / "api" / "routers.py"
    text = routers.read_text(encoding="utf-8")
    for name in EXAMPLES:
        text = text.replace(f"\n    {name}.router,", "")
        text = re.sub(rf"(from app\.api\.v1 import [^\n]*)\b{name}\b,? ?", r"\1", text)
    text = re.sub(r"from app\.api\.v1 import\s*\n", "", text)
    routers.write_text(text, encoding="utf-8")
    index = PROJECT / "doc" / "README.md"
    lines = index.read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if not any(line.startswith(f"| {name} |") for name in EXAMPLES)]
    index.write_text("\n".join(kept) + "\n", encoding="utf-8")


# 用临时的 SQLite 数据库生成只含框架表的初始迁移，再重新生成文档。
def regenerate() -> None:
    work = ROOT / "var" / "remove_examples.db"
    work.unlink(missing_ok=True)
    env = {**os.environ, "APP_DATABASE_URL": f"sqlite+aiosqlite:///{work}"}
    message = "create framework tables"
    commands = [
        [sys.executable, "-m", "alembic", "revision", "--autogenerate", "-m", message],
        [sys.executable, "-m", "ruff", "check", "--fix", "--quiet", "."],
        [sys.executable, "-m", "ruff", "format", "--quiet", "."],
        [sys.executable, "-m", "tools.export_docs"],
    ]
    for command in commands:
        subprocess.run(command, cwd=ROOT, env=env, check=True)
    work.unlink(missing_ok=True)


# 解析参数并删除示例。
def main() -> None:
    parser = argparse.ArgumentParser(description="删除两个示例模块")
    parser.add_argument("--yes", action="store_true", help="确认删除；不加时只列出将删除的内容")
    args = parser.parse_args()
    paths = example_paths()
    for path in paths:
        print(f"{'删除' if args.yes else '将删除'}：{path.relative_to(PROJECT)}")
    if not args.yes:
        print("确认是还没有真实数据的新项目后，加 --yes 执行。")
        return
    for path in paths:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    unregister()
    regenerate()
    print("已删除示例模块。接下来用 tools.new_module 生成自己的模块，并运行 tools.check。")


if __name__ == "__main__":
    main()
