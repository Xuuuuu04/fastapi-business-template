"""
生成一个新业务模块的完整骨架，并登记到模块总目录和路由清单：
  uv run python -m tools.new_module customer_contact --title 客户联系人
生成内容：service/模块名、doc/模块名、app/api/v1/模块名.py，
以及 tests/modules 与 tests/integration 下的测试。
生成后按提示补写业务文档、生成迁移、导出文档，再运行全量检查。
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from string import Template

from fastapi_check.quality.rules import PROJECT, ROOT, VAGUE_NAMES
from fastapi_module.registry import write_registry

TEMPLATES = Path(__file__).resolve().parents[2] / "assets/templates"
NAME = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$")


# 列出模板文件和生成位置。
def targets(name: str) -> dict[str, Path]:
    service = ROOT / "service" / name
    return {
        "service/README.md.txt": service / "README.md",
        "service/calc_README.md.txt": service / "calc" / "README.md",
        "service/calc/titles.py.txt": service / "calc" / "titles.py",
        "tests/test_calc.py.txt": ROOT / "tests" / "modules" / name / "test_calc.py",
        "service/data.py.txt": service / "data.py",
        "service/public.py.txt": service / "public.py",
        "service/flow.py.txt": service / "flow.py",
        "service/module.py.txt": service / "module.py",
        "service/module.json.txt": service / "module.json",
        "service/steps_README.md.txt": service / "steps" / "README.md",
        "service/steps/check_record.py.txt": service / "steps" / "check_record.py",
        "service/steps/store_records.py.txt": service / "steps" / "store_records.py",
        "service/store_README.md.txt": service / "store" / "README.md",
        "service/store/contract.py.txt": service / "store" / "contract.py",
        "service/store/sql.py.txt": service / "store" / "sql.py",
        "service/store/tables.py.txt": service / "store" / "tables.py",
        "doc/needs.md.txt": PROJECT / "doc" / name / "needs.md",
        "doc/rules.md.txt": PROJECT / "doc" / name / "rules.md",
        "doc/changes.md.txt": PROJECT / "doc" / name / "changes.md",
        "tests/test_steps.py.txt": ROOT / "tests" / "modules" / name / "test_records.py",
        "tests/test_api.py.txt": ROOT / "tests" / "integration" / name / "test_records.py",
        "api/routes.py.txt": ROOT / "app" / "api" / "v1" / f"{name}.py",
    }


# 检查模块名：小写下划线、至少两个词、不用含义模糊的词、不与现有模块重名。
def check_name(name: str) -> str:
    if not NAME.match(name):
        return "模块名只能用小写字母、数字和下划线，并且至少两个词，例如 customer_contact"
    if set(name.split("_")) & VAGUE_NAMES:
        return f"模块名中不要使用含义模糊的词：{', '.join(sorted(VAGUE_NAMES))}"
    if (ROOT / "service" / name).exists():
        return f"模块 {name} 已经存在"
    if (ROOT / "library" / name).exists():
        return f"工具包 {name} 已经存在，业务包不能与工具包同名"
    return ""


# 按模板生成全部文件。
def write_files(name: str, title: str) -> list[Path]:
    values = {"name": name, "title": title, "Camel": camel(name), "path": name.replace("_", "-")}
    written = []
    for source, target in targets(name).items():
        text = Template((TEMPLATES / source).read_text(encoding="utf-8")).substitute(values)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        written.append(target)
    return written


# 在模块总目录、路由清单和业务文档目录中登记新模块。
def register(name: str, title: str) -> list[Path]:
    catalog = ROOT / "app" / "setup" / "catalog.py"
    write_registry(ROOT)
    routers = ROOT / "app" / "api" / "routers.py"
    routers.write_text(add_route(routers.read_text(encoding="utf-8"), name), encoding="utf-8")
    add_doc_row(name, title)
    return [catalog, routers]


# 在模块总目录中导入并启用新模块。
def add_module(text: str, name: str) -> str:
    head = "MODULES: list[Module]"
    text = add_import(text, head, f"from service.{name}.module import module as {name}")
    return append_item(text, head, name)


# 在路由清单中导入并登记新模块的接口。
def add_route(text: str, name: str) -> str:
    head = "MODULE_ROUTERS: dict[str, tuple[APIRouter, ...]]"
    position = text.index(head)
    match = re.search(re.escape(head) + r" = \{(.*?)\}", text[position:], re.DOTALL)
    if match is None:
        raise SystemExit("找不到模块路由清单，请检查 app/api/routers.py")
    end = position + match.end() - 1
    text = text[:end] + f'\n    "{name}": ({name}.router,),' + text[end:]
    imports_end = text.index("ROUTERS: list[APIRouter]")
    return text[:imports_end] + f"from app.api.v1 import {name}\n\n" + text[imports_end:]


# 把导入放在列表定义之前，之后由 ruff 并入导入区；不依赖已有导入行的写法。
def add_import(text: str, head: str, line: str) -> str:
    position = text.find(f"{head} = [")
    if position < 0:
        raise SystemExit(f"找不到 {head}，请手工加入：{line}")
    return text[:position] + f"{line}\n\n" + text[position:]


# 在“名称 = [...]”形式的列表末尾加一项，不依赖列表写成一行还是多行。
def append_item(text: str, head: str, item: str) -> str:
    match = re.search(re.escape(head) + r" = \[(.*?)\]", text, re.DOTALL)
    if match is None:
        raise SystemExit(f"找不到 {head}，请手工登记 {item}")
    items = [part.strip() for part in match.group(1).split(",") if part.strip()]
    body = "".join(f"    {part},\n" for part in [*items, item])
    return text[: match.start()] + f"{head} = [\n{body}]" + text[match.end() :]


# 在 doc/README.md 的模块表中加一行。
def add_doc_row(name: str, title: str) -> None:
    index = PROJECT / "doc" / "README.md"
    lines = index.read_text(encoding="utf-8").splitlines()
    start = lines.index("## 模块")
    end = next(i for i in range(start + 3, len(lines)) if not lines[i].startswith("|"))
    links = " · ".join(
        f"[{label}]({name}/{file})"
        for label, file in (
            ("需求", "needs.md"),
            ("规则", "rules.md"),
            ("变化", "changes.md"),
            ("流程", "flows.md"),
        )
    )
    lines.insert(end, f"| {name} | {title} | {links} |")
    index.write_text("\n".join(lines) + "\n", encoding="utf-8")


# 把模块名转成驼峰写法，例如 customer_contact 转成 CustomerContact。
def camel(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


# 整理生成和修改过的 Python 文件的导入顺序与格式。
def tidy(paths: list[Path]) -> None:
    files = [str(path) for path in paths if path.suffix == ".py"]
    ruff = [sys.executable, "-m", "ruff"]
    subprocess.run([*ruff, "format", "--quiet", *files], cwd=ROOT, check=False)
    subprocess.run([*ruff, "check", "--fix", "--quiet", *files], cwd=ROOT, check=False)
    subprocess.run([*ruff, "format", "--quiet", *files], cwd=ROOT, check=False)


# 解析参数并生成模块。
def main() -> None:
    parser = argparse.ArgumentParser(description="生成新业务模块的骨架")
    parser.add_argument("name", help="模块名，至少两个词，例如 customer_contact")
    parser.add_argument("--title", required=True, help="模块中文名，例如 客户联系人")
    parser.add_argument("--kind", choices=["capability", "workflow"], default="capability")
    args = parser.parse_args()
    problem = check_name(args.name)
    if problem:
        sys.exit(problem)
    written = write_files(args.name, args.title)
    marker = ROOT / "service" / args.name / "module.json"
    import json

    descriptor = json.loads(marker.read_text())
    descriptor["kind"] = args.kind
    marker.write_text(json.dumps(descriptor, ensure_ascii=False, indent=2) + "\n")
    module = ROOT / "service" / args.name / "module.py"
    module.write_text(module.read_text().replace('kind="capability"', f'kind="{args.kind}"'))
    tidy(written + register(args.name, args.title))
    print(f"已生成模块 {args.name}（{args.title}），共 {len(written)} 个文件，并已登记。接下来：")
    print(
        f"1. 在 doc/{args.name}/needs.md 和 rules.md 写清真实业务，再按业务修改 service/{args.name}"
    )
    print("2. uv run alembic upgrade head（本地数据库需要先到最新版本才能比较出新表）")
    print(f'   uv run alembic revision --autogenerate -m "add {args.name} tables"，检查生成的迁移')
    print("3. uv run python ../.agents/skills/fastapi-docs/scripts/run_docs.py export_docs")
    print(
        "4. uv run python ../.agents/skills/fastapi-check/scripts/run_check.py "
        f"check --module {args.name}（先检查本模块）"
    )
    print(
        "5. uv run python ../.agents/skills/fastapi-check/scripts/run_check.py "
        "check（交付前检查全部模块）"
    )


if __name__ == "__main__":
    main()
