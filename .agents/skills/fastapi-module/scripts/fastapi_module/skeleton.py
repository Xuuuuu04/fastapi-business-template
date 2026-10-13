"""
从明确规格生成一批连接骨架；预览无写入，输入与业务预期由独立样例提供。
"""

import argparse
import ast
import json
from pathlib import Path

from fastapi_check.quality.rules import PROJECT
from fastapi_module.editing import write
from fastapi_module.new_module import tidy
from fastapi_module.new_operation import update_docs
from fastapi_module.registry import registry_text
from fastapi_module.skeleton_files import bundle_files
from fastapi_template.template.files import safe_path
from fastapi_module.skeleton_spec import SkeletonBundle
from fastapi_project.development.task_models import source_snapshot


# 派生登记之外的自定义逻辑不能被生成器静默覆盖。
def check_registry(project: Path) -> None:
    actual = (project / "server/app/setup/catalog.py").read_text()
    expected = registry_text(project / "server")

    # 仅忽略说明和导入排序，保留登记表达式与所有其他实际代码。
    def shape(text: str) -> tuple:
        body = [
            node
            for node in ast.parse(text).body
            if not (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            )
        ]
        imports = sorted(
            ast.dump(node) for node in body if isinstance(node, ast.Import | ast.ImportFrom)
        )
        rest = [
            ast.dump(node) for node in body if not isinstance(node, ast.Import | ast.ImportFrom)
        ]
        return imports, rest

    if shape(actual) != shape(expected):
        raise ValueError("登记文件含有独立逻辑，请先整理后再生成骨架")


# 生成之前验证全批，文档和格式处理失败会明确保留待处理的源码状态。
def generate(project: Path, spec: Path, *, preview: bool = False) -> list[str]:
    bundle = SkeletonBundle.model_validate_json(spec.read_bytes())
    check_registry(project)
    files = bundle_files(project, bundle)
    before = source_snapshot(project)
    written = write(files, preview=preview)
    if preview:
        return written
    tidy(list(files))
    update_docs()
    after = source_snapshot(project)
    return sorted(
        name for name in before.keys() | after.keys() if before.get(name) != after.get(name)
    )


# 模板只填类型占位和准确引用；业务值由人独立填写，已有资料不覆盖。
def initialize_cases(project: Path, spec: Path, *, preview: bool = False) -> list[str]:
    bundle = SkeletonBundle.model_validate_json(spec.read_bytes())
    bundle.validate_links()
    defaults = {
        "str": "待填写", "int": 0, "float": 0.0, "bool": False,
        "list[str]": [], "list[int]": [], "dict[str, str]": {}, "dict[str, int]": {},
    }
    files = {}
    for package in bundle.packages:
        folder = project / "doc" / package.name / "cases"
        existing = set()
        for path in folder.glob("*.json"):
            safe_path(project, path.relative_to(project).as_posix())
            try:
                existing.add(json.loads(path.read_text())["id"])
            except (ValueError, KeyError) as error:
                raise ValueError(f"{path.relative_to(project)}：无法读取已有样例编号") from error
        rules = project / "doc" / package.name / "rules.md"
        if not rules.exists():
            ids = sorted({case.split(".")[1].split("-C")[0]
                          for op in package.operations for case in op.cases})
            files[rules] = f"# {package.title}\n\n" + "\n".join(
                f"### {identity} 待填写规则\n\n待确认：请填写业务条件与异常。\n" for identity in ids
            )
        for operation in package.operations:
            for identity in operation.cases:
                path = project / "doc" / package.name / "cases" / (identity + ".json")
                if path.exists() or identity in existing:
                    continue
                files[path] = json.dumps({
                    "id": identity,
                    "input": {name: defaults[field.type] for name, field in operation.input.items()},
                    "initial": {},
                    "expected": {name: defaults[field.type] for name, field in operation.output.items()},
                    "assertions": ["待填写：请独立确认输入与预期的业务含义"],
                    "tests": [f"tests/modules/{package.name}/test_{operation.name}.py::test_case"],
                }, ensure_ascii=False, indent=2) + "\n"
    for path in files:
        safe_path(project, path.relative_to(project).as_posix())
    if not preview:
        for path, text in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    return [path.relative_to(project).as_posix() for path in files]


# 命令不从实现推断规格，也不生成模型任务或启动代理。
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--init", action="store_true", help="生成不覆盖的独立样例与规则模板，填好业务值后再生成骨架")
    args = parser.parse_args()
    action = initialize_cases if args.init else generate
    files = action(PROJECT, args.spec.resolve(), preview=args.preview)
    print(
        json.dumps(
            {"preview": args.preview, "files": files,
             "implementation": "case_templates" if args.init else "skeleton",
             "next": "填写 doc/包名/cases/*.json 的业务值和 rules.md 后运行 uv run dev skeleton --spec "
             + str(args.spec) if args.init else "uv run dev start --package 包名 --cases R-01-C01"},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
