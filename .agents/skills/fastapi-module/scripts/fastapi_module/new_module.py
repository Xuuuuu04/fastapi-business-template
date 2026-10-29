import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from string import Template

from fastapi_check.quality.rules import ROOT, VAGUE_NAMES
from fastapi_module.registry import write_registry

TEMPLATES = Path(__file__).resolve().parents[2] / "assets/templates"
NAME = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$")


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
        "tests/test_steps.py.txt": ROOT / "tests" / "modules" / name / "test_records.py",
        "tests/test_api.py.txt": ROOT / "tests" / "integration" / name / "test_records.py",
        "api/routes.py.txt": ROOT / "app" / "api" / "v1" / f"{name}.py",
    }


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


def write_files(name: str, title: str) -> list[Path]:
    values = {"name": name, "title": title, "Camel": camel(name), "path": name.replace("_", "-")}
    written = []
    for source, target in targets(name).items():
        text = Template((TEMPLATES / source).read_text(encoding="utf-8")).substitute(values)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        written.append(target)
    return written


def register(name: str, title: str) -> list[Path]:
    catalog = ROOT / "app" / "setup" / "catalog.py"
    write_registry(ROOT)
    routers = ROOT / "app" / "api" / "routers.py"
    routers.write_text(add_route(routers.read_text(encoding="utf-8"), name), encoding="utf-8")
    return [catalog, routers]


def add_module(text: str, name: str) -> str:
    head = "MODULES: list[Module]"
    text = add_import(text, head, f"from service.{name}.module import module as {name}")
    return append_item(text, head, name)


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


def add_import(text: str, head: str, line: str) -> str:
    position = text.find(f"{head} = [")
    if position < 0:
        raise SystemExit(f"找不到 {head}，请手工加入：{line}")
    return text[:position] + f"{line}\n\n" + text[position:]


def append_item(text: str, head: str, item: str) -> str:
    match = re.search(re.escape(head) + r" = \[(.*?)\]", text, re.DOTALL)
    if match is None:
        raise SystemExit(f"找不到 {head}，请手工登记 {item}")
    items = [part.strip() for part in match.group(1).split(",") if part.strip()]
    body = "".join(f"    {part},\n" for part in [*items, item])
    return text[: match.start()] + f"{head} = [\n{body}]" + text[match.end() :]


def camel(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def tidy(paths: list[Path]) -> None:
    files = [str(path) for path in paths if path.suffix == ".py"]
    ruff = [sys.executable, "-m", "ruff"]
    subprocess.run([*ruff, "format", "--quiet", *files], cwd=ROOT, check=False)
    subprocess.run([*ruff, "check", "--fix", "--quiet", *files], cwd=ROOT, check=False)
    subprocess.run([*ruff, "format", "--quiet", *files], cwd=ROOT, check=False)


def set_kind(name: str, kind: str) -> None:
    marker = ROOT / "service" / name / "module.json"
    descriptor = json.loads(marker.read_text())
    descriptor["kind"] = kind
    marker.write_text(json.dumps(descriptor, ensure_ascii=False, indent=2) + "\n")
    module = ROOT / "service" / name / "module.py"
    module.write_text(module.read_text().replace('kind="capability"', f'kind="{kind}"'))


def next_steps(name: str) -> list[str]:
    return [
        f"1. 按真实业务修改 service/{name}",
        "2. uv run alembic upgrade head（本地数据库需要先到最新版本才能比较出新表）",
        f'   uv run alembic revision --autogenerate -m "add {name} tables"，检查生成的迁移',
        "3. uv run dev docs（更新 openapi.json）",
        f"4. uv run dev check --module {name}（先检查本模块）",
        "5. uv run dev check（交付前检查全部模块）",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="生成新业务模块的骨架")
    parser.add_argument("name", help="模块名，至少两个词，例如 customer_contact")
    parser.add_argument("--title", required=True, help="模块中文名，例如 客户联系人")
    parser.add_argument("--kind", choices=["capability", "workflow"], default="capability")
    parser.add_argument(
        "--preset",
        choices=["access"],
        help="access：最小账号包（登录、新建账号、账号表迁移），接口路径固定为 /api/v1/access",
    )
    args = parser.parse_args()
    problem = check_name(args.name)
    if problem:
        sys.exit(problem)
    if args.preset:
        from fastapi_module import access_preset

        if args.kind != "capability":
            parser.error("账号包只能是能力包")
        written = access_preset.write_preset(args.name, args.title)
        steps = access_preset.next_steps(args.name)
    else:
        written = write_files(args.name, args.title)
        set_kind(args.name, args.kind)
        steps = next_steps(args.name)
    tidy(written + register(args.name, args.title))
    print(f"已生成模块 {args.name}（{args.title}），共 {len(written)} 个文件，并已登记。接下来：")
    print("\n".join(steps))


if __name__ == "__main__":
    main()
