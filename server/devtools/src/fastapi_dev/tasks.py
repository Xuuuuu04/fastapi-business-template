"""
start创建开工卡，finish实际运行相关检查；契约修改请求只生成资料，不改公开接口。
"""

import argparse
import json
import uuid
from pathlib import Path

from fastapi_check.check import execute
from fastapi_check.matrix import CheckOptions
from fastapi_check.quality.rules import PROJECT
from fastapi_project.development.check_assets import atomic_bytes
from fastapi_project.development.history import read_checks
from fastapi_project.development.selection import Selection
from fastapi_project.development.task_baseline import review_pack
from fastapi_project.development.task_models import read_card
from fastapi_project.development.tasks import finish_task, related_modules, start_task
from fastapi_project.panel import generate

from app.setup.application import application_modules
from shared.modules.catalog import Catalog


# 完成必须使用命令这次实际生成的唯一记录，多个并发轮次不混成一个结论。
def finish(project: Path, catalog: Catalog, identity: str, postgres: str) -> dict:
    card = read_card(project, identity)
    selected = related_modules(catalog, card.package)
    before = {check["id"] for check in read_checks(project, include_cases=False)}
    execute(
        Selection(modules=selected),
        postgres,
        CheckOptions(
            database="both" if postgres else "sqlite",
            workers=1,
            delivery=True,
        ),
    )
    fresh = [
        check for check in read_checks(project, include_cases=False) if check["id"] not in before
    ]
    if len(fresh) != 1:
        raise ValueError("没有唯一的本次检查记录，不能据此完成任务")
    workflow = any(
        catalog.modules[name].kind == "workflow" or catalog.modules[name].pipelines
        for name in selected
    )
    required = ("sqlite", "postgresql") if postgres or workflow else ("sqlite",)
    completed = finish_task(project, catalog, card, fresh[0], required)
    panel = generate(project, catalog)
    return {
        "id": completed.id,
        "state": completed.state,
        "checks": completed.checks,
        "outside": completed.outside,
        "problems": completed.problems,
        "review": f".agents/records/reviews/{completed.id}.json",
        "panel": panel.relative_to(project).as_posix(),
    }


# 契约变更只保存请求，不改契约，也不假定主代理已经批准。
def ask_contract(project: Path, package: str, reason: str, suggestion: str) -> Path:
    if not package or any(
        character not in "abcdefghijklmnopqrstuvwxyz0123456789_" for character in package
    ):
        raise ValueError("业务包名称不合法")
    identity = uuid.uuid4().hex
    path = project / ".agents/records/contract-requests" / (identity + ".json")
    atomic_bytes(
        path,
        json.dumps(
            {
                "id": identity,
                "package": package,
                "reason": reason,
                "suggestion": suggestion,
                "state": "pending",
            },
            ensure_ascii=False,
            indent=2,
        ).encode(),
    )
    return path


# 实际项目由统一dev入口选定，摘要不展开数百份源码基线和任何数据库地址。
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "finish", "ask-contract", "review-pack"])
    parser.add_argument("--package")
    parser.add_argument("--cases")
    parser.add_argument("--task")
    parser.add_argument("--postgres", default="")
    parser.add_argument("--reason")
    parser.add_argument("--suggestion")
    args = parser.parse_args()
    catalog = Catalog(application_modules())
    if args.action == "start":
        if not args.package or not args.cases:
            parser.error("start需要--package和--cases")
        card = start_task(PROJECT, catalog, args.package, args.cases.split(","))
        result = card.model_dump(exclude={"before"})
        result["task_file"] = f".agents/records/tasks/{card.id}.json"
    elif args.action == "finish":
        if not args.task:
            parser.error("finish需要--task")
        result = finish(PROJECT, catalog, args.task, args.postgres)
    elif args.action == "review-pack":
        if not args.task:
            parser.error("review-pack需要--task")
        path = review_pack(PROJECT, read_card(PROJECT, args.task))
        result = {"file": path.relative_to(PROJECT).as_posix()}
    else:
        if not args.package or not args.reason or not args.suggestion:
            parser.error("ask-contract需要包、原因和建议")
        path = ask_contract(PROJECT, args.package, args.reason, args.suggestion)
        result = {"file": path.relative_to(PROJECT).as_posix(), "state": "pending"}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("state") in {"incomplete", "needs_update"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
