"""
新增公开操作的一次生成：Data、步骤、flow、登记、可选HTTP、规则和短测试，先预览实际改动。
"""

import argparse
import ast
import json
import re
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


# 在已有模块里计算完整改动，不覆写已登记同名操作。
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

    # 虚拟改动让一条流程的多个操作共用尚未写入的更新。
    def read(path: Path) -> str:
        return base[path] if path in base else path.read_text()

    folder = validate(module, name)
    public = read(folder / "public.py")
    check_new_name(public, module, name)
    rules = PROJECT / "doc" / module / "rules.md"
    text = read(rules)
    numbers = [int(value) for value in re.findall(r"^### R-(\d+)", text, re.MULTILINE)]
    rule = f"R-{max(numbers, default=0) + 1:02}"
    models, input, output, invalid = templates.data(name, module, rule, state)
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
        f"access={module + '.run'!r}, errors=({invalid},))\n__all__ += {sorted(set(exports))!r}"
    )
    public = add_import(public, f"from service.{module}.data import {input}, {output}, {invalid}")
    generated[folder / "public.py"] = append(public, declaration)
    generated |= implementation_files(module, name, title, kind, output, invalid, rule, read)
    registration = folder / "module.py"
    generated[registration] = extend_module(
        read(registration),
        "provides",
        f"public.{name}: flow.{name}_flow",
        mapping=True,
    )
    generated |= supporting_files(module, name, title, input, invalid, rule, read)
    if http:
        generated |= route(module, name, title, input, output)
    return generated


# 步骤和Flow一起连接，避免只创建函数却忘登记执行链。
def implementation_files(
    module: str,
    name: str,
    title: str,
    kind: str,
    output: str,
    invalid: str,
    rule: str,
    read: Callable[[Path], str],
) -> dict[Path, str]:
    folder = ROOT / "service" / module
    generated: dict[Path, str] = {}
    step = folder / "steps" / f"build_{name}.py"
    generated[step] = templates.step_code(module, name, rule, output, invalid)
    flow = folder / "flow.py"
    flow_text = add_import(read(flow), f"from service.{module}.data import {kind}Work")
    flow_text = add_import(
        flow_text, f"from service.{module}.steps.build_{name} import build_{name}"
    )
    generated[flow] = append(
        flow_text,
        f"{name}_flow = Flow({title!r}, work={kind}Work, result='result', steps=[build_{name}])",
    )
    return generated


# 测试、规则与模块公开列表作为同一批配套改动，夹具只生成一次。
def supporting_files(
    module: str,
    name: str,
    title: str,
    input: str,
    invalid: str,
    rule: str,
    read: Callable[[Path], str],
) -> dict[Path, str]:
    folder = ROOT / "service" / module
    rules = PROJECT / "doc" / module / "rules.md"
    text = read(rules)
    generated: dict[Path, str] = {}
    generated[rules] = append(text, rule_doc(rule, module, title))
    tests = ROOT / "tests/modules" / module
    generated[tests / f"test_{name}.py"] = templates.tests(module, name, input, invalid, rule)
    fixture = tests / "conftest.py"
    if not fixture.exists() and not _has_fixture(read, fixture):
        generated[fixture] = templates.fixture()
    elif "operation_services" not in read(fixture):
        generated[fixture] = append(read(fixture), templates.fixture())
    readme = folder / "README.md"
    generated[readme] = read(readme).replace(
        "## 公开操作", f"## 公开操作\n\n- `{module}.{name}`：{title}。", 1
    )
    return generated


# 虚拟更新可能先生成夹具，缺少文件时明确返回False。
def _has_fixture(read: Callable[[Path], str], path: Path) -> bool:
    try:
        return "operation_services" in read(path)
    except FileNotFoundError:
        return False


# 规则占位有可运行样例，不把样例规则当正式业务验收。
def rule_doc(rule: str, module: str, title: str) -> str:
    return f"""### {rule} {title}生成样例

生成占位：样例文本去掉首尾空白，空文本拒绝；正式业务判断待确认，需替换本规则与样例。

| 样例编号 | 情况 | 结果 |
| --- | --- | --- |
| {rule}-C01 | 文本带首尾空白 | 去掉空白后返回 |
| {rule}-C02 | 全空白 | 对应规则异常 |
"""


# 路由只通过public及RunDep调用，登记复用已有模块router。
def route(module: str, name: str, title: str, input: str, output: str) -> dict[Path, str]:
    path = ROOT / "app/api/v1" / f"{module}.py"
    if not path.is_file():
        raise ValueError("可选HTTP需要已登记的模块router，请先创建标准模块")
    code = f'''
# 调用生成的公开操作，不在HTTP层计算业务。
@router.post("/{name.replace("_", "-")}", summary={title!r}, operation_id="{module}_{name}",
             response_model={module}.{output})
async def {name}(body: {module}.{input}, run: RunDep) -> {module}.{output}:
    return await run({module}.{name}, body)
'''
    return {path: append(path.read_text(), code)}


# 执行后整理生成内容并同步文档入口；预览不写文件、不登记。
def generate(
    module: str, name: str, title: str, *, http: bool = False, preview: bool = False
) -> list[str]:
    values = changes(module, name, title, http=http)
    docs = [
        PROJECT / "AGENTS.md",
        PROJECT / "project-plan.json",
        PROJECT / "doc/api/openapi.json",
        PROJECT / "doc/api/index.md",
        PROJECT / "doc" / module / "flows.md",
    ]
    before = snapshot([*values, *docs])
    written = write(values, preview=preview)
    if not preview:
        tidy(list(values))
        update_docs()
        written = [
            str(path.relative_to(PROJECT))
            for path, old in before.items()
            if path.exists() and path.read_text() != old
        ]
    return written


# 使用项目文档命令生成入口和flows，记录实际后处理改动。
def update_docs() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "../.agents/skills/fastapi-docs/scripts/run_docs.py",
            "export_docs",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise ValueError("生成源码已保存，文档登记失败：" + result.stdout + result.stderr)


# 参数和改动文件清单可作为后续影响报告的对照。
def main() -> None:
    parser = argparse.ArgumentParser(description="新增操作、可选HTTP和短规则样例")
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
    print(json.dumps(dict(files=files, preview=args.preview), ensure_ascii=False, indent=2))


# 同名操作不覆写，生成前检查所有已有公开赋值。
def check_new_name(public: str, module: str, name: str) -> None:
    if any(
        isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
        for node in ast.parse(public).body
    ):
        raise ValueError(f"操作{module}.{name}已经存在")


if __name__ == "__main__":
    main()
