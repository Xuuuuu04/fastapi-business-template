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
from fastapi_module.skeleton_spec import SkeletonBundle, SkeletonPackage
from fastapi_template.template.files import safe_path


def check_registry(project: Path) -> None:
    actual = (project / "server/app/setup/catalog.py").read_text()
    expected = registry_text(project / "server")

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


def generate(project: Path, spec: Path, *, preview: bool = False) -> list[str]:
    bundle = SkeletonBundle.model_validate_json(spec.read_bytes())
    check_registry(project)
    files = bundle_files(project, bundle)
    written = write(files, preview=preview)
    if not preview:
        tidy(list(files))
        update_docs()
    return written


def existing_cases(project: Path, folder: Path) -> set[str]:
    existing: set[str] = set()
    for path in folder.glob("*.json"):
        safe_path(project, path.relative_to(project).as_posix())
        try:
            existing.add(json.loads(path.read_text())["id"])
        except (ValueError, KeyError) as error:
            raise ValueError(f"{path.relative_to(project)}：无法读取已有样例编号") from error
    return existing


def case_templates(project: Path, package: SkeletonPackage) -> dict[Path, str]:
    defaults = {
        "str": "待填写",
        "int": 0,
        "float": 0.0,
        "bool": False,
        "list[str]": [],
        "list[int]": [],
        "dict[str, str]": {},
        "dict[str, int]": {},
    }
    files = {}
    folder = project / "doc" / package.name / "cases"
    existing = existing_cases(project, folder)
    for operation in package.operations:
        for identity in operation.cases:
            path = folder / (identity + ".json")
            if path.exists() or identity in existing:
                continue
            files[path] = (
                json.dumps(
                    {
                        "id": identity,
                        "input": {
                            name: defaults[field.type] for name, field in operation.input.items()
                        },
                        "initial": {},
                        "expected": {
                            name: defaults[field.type] for name, field in operation.output.items()
                        },
                        "assertions": ["待填写：请独立确认输入与预期的业务含义"],
                        "tests": [
                            f"tests/modules/{package.name}/test_{operation.name}.py::test_case"
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            )
    return files


def initialize_cases(project: Path, spec: Path, *, preview: bool = False) -> list[str]:
    bundle = SkeletonBundle.model_validate_json(spec.read_bytes())
    bundle.validate_links()
    files = {}
    for package in bundle.packages:
        files.update(case_templates(project, package))
    for path in files:
        safe_path(project, path.relative_to(project).as_posix())
    if not preview:
        for path, text in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    return [path.relative_to(project).as_posix() for path in files]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument(
        "--init",
        action="store_true",
        help="生成不覆盖的独立样例与规则模板，填好业务值后再生成骨架",
    )
    args = parser.parse_args()
    action = initialize_cases if args.init else generate
    files = action(PROJECT, args.spec.resolve(), preview=args.preview)
    print(
        json.dumps(
            {
                "preview": args.preview,
                "files": files,
                "implementation": "case_templates" if args.init else "skeleton",
                "next": "填写 doc/包名/cases/*.json 的业务值后运行 "
                + f"uv run dev skeleton --spec {args.spec}"
                if args.init
                else "uv run dev check --module 包名",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
