import argparse
import ast
import json
from collections.abc import Callable
from pathlib import Path

from fastapi_check.quality.rules import PROJECT, ROOT
from fastapi_module import operation_templates as templates
from fastapi_module.editing import (
    add_import,
    append,
    extend_module,
    snapshot,
    validate,
    write,
)
from fastapi_module.new_module import camel, tidy


def changes(
    module: str,
    name: str,
    title: str,
    *,
    http: bool = False,
    state: str = "",
    base: dict[Path, str] | None = None,
) -> dict[Path, str]:
    base = base or {}

    def read(path: Path) -> str:
        return base[path] if path in base else path.read_text()

    folder = validate(module, name)
    public = read(folder / "public.py")
    check_new_name(public, module, name)
    models, input, output, invalid = templates.data(name, module, state)
    kind = camel(name)
    data_path = folder / "data.py"
    generated = {data_path: append(read(data_path), models)}
    generated[data_path] = add_import(
        generated[data_path],
        "from shared.public import BusinessError, Data, Kind, WorkData, meaning",
    )
    exports = [name, input, output, invalid]
    declaration = (
        f"{name} = contract({module + '.' + name!r}, {title!r}, input={input}, output={output}, "
        f"access={module + '.run'!r}, effect='query', errors=({invalid},))\n"
        f"__all__ += {sorted(set(exports))!r}"
    )
    public = add_import(public, f"from service.{module}.data import {input}, {output}, {invalid}")
    public = add_import(public, "from shared.public import contract")
    generated[folder / "public.py"] = append(public, declaration)
    generated |= implementation_files(module, name, title, kind, output, invalid, read)
    registration = folder / "module.py"
    generated[registration] = extend_module(
        add_import(read(registration), f"from service.{module} import flow, public"),
        "provides",
        f"public.{name}: flow.{name}_flow",
        mapping=True,
    )
    generated |= supporting_files(module, name, input, invalid, read)
    if http:
        generated |= route(module, name, title, input, output)
    return generated


def implementation_files(
    module: str,
    name: str,
    title: str,
    kind: str,
    output: str,
    invalid: str,
    read: Callable[[Path], str],
) -> dict[Path, str]:
    folder = ROOT / "service" / module
    generated: dict[Path, str] = {}
    step = folder / "steps" / f"build_{name}.py"
    generated[step] = templates.step_code(module, name, output, invalid)
    generated[folder / "calc" / f"{name}.py"] = templates.calc_code()
    flow = folder / "flow.py"
    flow_text = add_import(read(flow), "from shared.public import Flow")
    flow_text = add_import(flow_text, f"from service.{module}.data import {kind}Work")
    flow_text = add_import(
        flow_text, f"from service.{module}.steps.build_{name} import build_{name}"
    )
    generated[flow] = append(
        flow_text,
        f"{name}_flow = Flow({title!r}, work={kind}Work, result='result', steps=[build_{name}])",
    )
    return generated


def supporting_files(
    module: str, name: str, input: str, invalid: str, read: Callable[[Path], str]
) -> dict[Path, str]:
    generated: dict[Path, str] = {}
    tests = ROOT / "tests/modules" / module
    generated[tests / f"test_calc_{name}.py"] = templates.calc_tests(module, name)
    generated[tests / f"test_{name}.py"] = templates.tests(module, name, input, invalid)
    fixture = tests / "conftest.py"
    if not fixture.exists() and not _has_fixture(read, fixture):
        generated[fixture] = templates.fixture()
    elif "operation_services" not in read(fixture):
        generated[fixture] = append(read(fixture), templates.fixture())
    return generated


def _has_fixture(read: Callable[[Path], str], path: Path) -> bool:
    try:
        return "operation_services" in read(path)
    except FileNotFoundError:
        return False


def route(module: str, name: str, title: str, input: str, output: str) -> dict[Path, str]:
    path = ROOT / "app/api/v1" / f"{module}.py"
    if not path.is_file():
        raise ValueError("可选HTTP需要已登记的模块router，请先创建标准模块")
    code = f'''
@router.post("/{name.replace("_", "-")}", summary={title!r}, operation_id="{module}_{name}",
             response_model={module}.{output})
async def {name}(body: {module}.{input}, run: RunDep) -> {module}.{output}:
    return await run({module}.{name}, body)
'''
    text = add_import(path.read_text(), "from app.api.runner import RunDep")
    text = add_import(text, f"from service.{module} import public as {module}")
    return {path: append(text, code)}


def generate(
    module: str, name: str, title: str, *, http: bool = False, preview: bool = False
) -> list[str]:
    values = changes(module, name, title, http=http)
    before = snapshot(list(values))
    written = write(values, preview=preview)
    if not preview:
        tidy(list(values))
        written = [
            str(path.relative_to(PROJECT))
            for path, old in before.items()
            if path.exists() and path.read_text() != old
        ]
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="新增操作和可选HTTP")
    parser.add_argument("module")
    parser.add_argument("name")
    parser.add_argument("--title", required=True)
    parser.add_argument("--http", action="store_true")
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    try:
        files = generate(args.module, args.name, args.title, http=args.http, preview=args.preview)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(
        json.dumps(
            dict(
                files=files,
                preview=args.preview,
                next="改了接口时运行 uv run dev docs 更新 openapi.json",
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


def check_new_name(public: str, module: str, name: str) -> None:
    if any(
        isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
        for node in ast.parse(public).body
    ):
        raise ValueError(f"操作{module}.{name}已经存在")


if __name__ == "__main__":
    main()
