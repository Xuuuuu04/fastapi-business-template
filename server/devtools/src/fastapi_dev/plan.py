import argparse
import json
from pathlib import Path

from fastapi_check.quality.rules import PROJECT
from fastapi_project.development.check_assets import atomic_bytes
from fastapi_project.development.plan import check_plan, read_plan


def save_plan(project: Path, plan: dict) -> None:
    check_plan(plan)
    atomic_bytes(
        project / "project-plan.json",
        (json.dumps(plan, ensure_ascii=False, indent=2) + "\n").encode(),
    )


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


def main() -> None:
    parser = argparse.ArgumentParser()
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
