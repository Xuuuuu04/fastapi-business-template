import argparse
import json
from pathlib import Path

from fastapi_check.quality.rules import PROJECT
from fastapi_module.editing import add_import, append, extend_module, snapshot, validate, write
from fastapi_module.new_module import camel, tidy
from fastapi_module.new_operation import changes as operation_changes
from fastapi_module.new_operation import update_docs


def changes(module: str, name: str, title: str, stages: list[str], wait: str) -> dict[Path, str]:
    folder = validate(module, name)
    if not stages or len(set(stages)) != len(stages) or wait not in stages:
        raise ValueError("需要不重复的阶段名称及属于该链的等待阶段")
    for stage in stages:
        validate(module, name + "_" + stage)
    state = camel(name) + "State"
    data = folder / "data.py"
    values = {
        data: append(
            add_import(data.read_text(), "from shared.public import Data, meaning"),
            f"class {state}(Data):\n"
            '    text: str = meaning("生成样例文本；业务实现后替换", default="样例")\n'
            '    ready: bool = meaning("等待结果是否就绪", default=False)',
        )
    }
    for stage in stages:
        operation = name + "_" + stage
        values |= operation_changes(
            module, operation, title + "：" + stage, state=state, base=values
        )
        step = folder / "steps" / f"build_{operation}.py"
        if stage == wait:
            values[step] = values[step].replace(
                f"{state}(text=value)", f"{state}(text=value, ready=True)"
            )
    readme = folder / "README.md"
    values[readme] = readme_text(values[readme], module, name, title)
    registration = folder / "module.py"
    values[registration] = registration_text(
        values[registration], module, name, title, state, stages, wait
    )
    config = PROJECT / "doc" / module / f"drill_{name}.json"
    values[config] = (
        json.dumps(
            dict(
                schema_version=1,
                pipeline=module + "." + name,
                entry="schedule",
                scale=100000,
                replay={},
                uncovered=stages,
                meaning="演练占位：阶段样例未覆盖真实业务，上游原件回放由PR4命令接入",
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    return values


def readme_text(original: str, module: str, name: str, title: str) -> str:
    entry = f"- `{module}.start_{name}`：启动{title}。"
    return original.replace("## 公开操作", "## 公开操作\n\n" + entry, 1)


def registration_text(
    original: str, module: str, name: str, title: str, state: str, stages: list[str], wait: str
) -> str:
    text = add_import(original, "from datetime import timedelta")
    text = add_import(
        text, "from shared.public import JobPlan, Pipeline, Schedule, Stage, StartRequest, Wait"
    )
    text = add_import(text, f"from service.{module}.data import {state}")
    specs = []
    for stage in stages:
        kind = "Wait" if stage == wait else "Stage"
        options = ", every=30, timeout=3600" if stage == wait else ""
        specs.append(f"{kind}({stage!r}, public.{name}_{stage}{options})")
    declaration = (
        f"{name}_pipeline = Pipeline({module + '.' + name!r}, {title!r}, {state}, "
        f"stages=({', '.join(specs)},))\n"
    )
    position = text.index("module = Module(")
    text = text[:position] + declaration + "\n" + text[position:]
    for stage in stages:
        text = extend_module(text, "jobs", f"JobPlan(public.{name}_{stage}, repeat_safe=True)")
    text = extend_module(text, "pipelines", f"{name}_pipeline")
    schedule = (
        f"Schedule({name!r}, {title!r}, {name}_pipeline.start, "
        f"{name}_pipeline.start.input(request=StartRequest[{state}](data={state}())), "
        'every=timedelta(days=1), slot_input_field="request.period")'
    )
    return extend_module(text, "schedules", schedule)


def generate(
    module: str, name: str, title: str, stages: list[str], wait: str, preview: bool = False
) -> list[str]:
    values = changes(module, name, title, stages, wait)
    docs = [PROJECT / "doc/api/openapi.json"]
    before = snapshot([*values, *docs])
    files = write(values, preview=preview)
    if not preview:
        tidy(list(values))
        update_docs()
        files = [
            str(path.relative_to(PROJECT))
            for path, old in before.items()
            if path.exists() and path.read_text() != old
        ]
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description="生成多阶段流程和定时/演练骨架")
    parser.add_argument("module")
    parser.add_argument("name")
    parser.add_argument("--title", required=True)
    parser.add_argument("--stages", default="select,collect,wait,publish")
    parser.add_argument("--wait", default="wait")
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    try:
        files = generate(
            args.module, args.name, args.title, args.stages.split(","), args.wait, args.preview
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(dict(files=files, preview=args.preview), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
