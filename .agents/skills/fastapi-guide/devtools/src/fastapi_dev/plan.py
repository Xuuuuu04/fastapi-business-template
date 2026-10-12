"""
项目图只维护业务计划，实际实现与依赖始终从源码读取；包级计划可以先于操作存在。
"""

import argparse
import json
from pathlib import Path

from fastapi_check.quality.rules import PROJECT
from fastapi_project.development.check_assets import atomic_bytes
from fastapi_project.development.plan import check_plan, read_plan


# 计划文件使用一次完整替换，避免写一半留下无法读取的JSON。
def save_plan(project: Path, plan: dict) -> None:
    check_plan(plan)
    atomic_bytes(
        project / "project-plan.json",
        (json.dumps(plan, ensure_ascii=False, indent=2) + "\n").encode(),
    )


# 模块类型与依赖只是计划，不能据此声称已经实现或通过检查。
def add_package(
    project: Path,
    name: str,
    title: str,
    line: str,
    kind: str,
    operations: list[str],
    dependencies: list[str],
) -> dict:
    plan = read_plan(project) or {"schema_version": 2, "name": project.name, "lines": []}
    plan["schema_version"] = 2
    packages = [package for group in plan["lines"] for package in group["packages"]]
    if any(package["module"] == name for package in packages):
        raise ValueError("开发包已经存在")
    group = next((group for group in plan["lines"] if group["name"] == line), None)
    if group is None:
        group = {"name": line, "packages": []}
        plan["lines"].append(group)
    group["packages"].append(
        dict(
            module=name,
            title=title,
            kind=kind,
            operations=operations,
            dependencies=sorted(set(dependencies)),
        )
    )
    save_plan(project, plan)
    return plan


# 命令不导入业务实现，也不创建数据库或假实现。
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("show")
    add = commands.add_parser("add-package")
    add.add_argument("name")
    add.add_argument("--title", required=True)
    add.add_argument("--line", default="主要业务")
    add.add_argument("--kind", choices=["capability", "workflow", "library"], default="capability")
    add.add_argument("--operation", action="append", default=[])
    add.add_argument("--depends", action="append", default=[])
    args = parser.parse_args()
    if args.command == "show":
        plan = read_plan(PROJECT)
    else:
        plan = add_package(
            PROJECT, args.name, args.title, args.line, args.kind, args.operation, args.depends
        )
    print(json.dumps(plan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
