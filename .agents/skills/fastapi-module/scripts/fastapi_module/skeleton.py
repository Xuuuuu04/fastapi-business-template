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


# 命令不从实现推断规格，也不生成模型任务或启动代理。
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    files = generate(PROJECT, args.spec.resolve(), preview=args.preview)
    print(
        json.dumps(
            {"preview": args.preview, "files": files, "implementation": "skeleton"},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
