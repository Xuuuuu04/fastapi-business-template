"""
规则账本命令：登记来源、推定、采纳、明确确认和废止；确认声明不证明操作人的真实身份。
"""

import argparse
from datetime import UTC, datetime
from pathlib import Path

from fastapi_check.quality.rules import PROJECT
from fastapi_project.development.ledger import add_source, confirm, propose, read_ledger, transition
from fastapi_project.development.ledger_models import LedgerRule, RuleConfirmation, RuleSource
from fastapi_project.development.ledger_store import recover_store
from fastapi_project.development.rule_documents import adopt_markdown, confirm_sheet, supersede


# 命令只改开发资料，不读取数据库和产品凭据；原文默认进入本机忽略目录。
def run(args: argparse.Namespace, project: Path) -> None:
    result: RuleSource | LedgerRule
    if run_document(args, project):
        return
    if args.action == "show":
        print(read_ledger(project).model_dump_json(indent=2))
        return
    if args.action == "source":
        raw = None
        if args.raw_file:
            path = Path(args.raw_file)
            if path.stat().st_size > 256_000:
                raise ValueError("原文超过单次材料上限，请保留外部原件和摘要引用")
            raw = path.read_text()
        result = add_source(
            project,
            RuleSource(id=args.id, kind=args.kind, summary=args.summary, locator=args.locator),
            raw=raw,
        )
    elif args.action == "propose":
        result = propose(
            project,
            LedgerRule(id=args.id, text=args.text, sources=args.source, risk=args.risk),
            reason=args.reason,
        )
    elif args.action in {"adopt", "retire"}:
        result = transition(
            project, args.id, "adopted" if args.action == "adopt" else "retired", reason=args.reason
        )
    else:
        result = confirm(
            project,
            args.id,
            RuleConfirmation(
                source=args.source,
                revision=args.revision,
                kind=args.kind,
                note=args.note,
                recorded_by=args.recorded_by,
                recorded_at=datetime.now(UTC).isoformat(),
            ),
        )
    print(result.model_dump_json(indent=2))


# 资料命令独立于生命周期写入，返回是否已处理当前命令。
def run_document(args: argparse.Namespace, project: Path) -> bool:
    if args.action == "recover":
        print("规则写入已恢复" if recover_store(project) else "没有未完成的规则写入")
        return True
    if args.action == "confirm_sheet":
        print(confirm_sheet(project))
        return True
    if args.action == "adopt_markdown":
        print(adopt_markdown(project, args.module))
        return True
    if args.action == "supersede":
        print(
            supersede(project, args.id, args.text, args.source, args.reason).model_dump_json(
                indent=2
            )
        )
        return True
    return False


# 原始材料和确认原因都显式提供，不从实现或运行成功反推业务预期。
def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("show")
    commands.add_parser("recover")
    commands.add_parser("confirm_sheet")
    imported = commands.add_parser("adopt_markdown")
    imported.add_argument("module")
    revised = commands.add_parser("supersede")
    revised.add_argument("id")
    revised.add_argument("--text", required=True)
    revised.add_argument("--source", required=True)
    revised.add_argument("--reason", required=True)
    source = commands.add_parser("source")
    source.add_argument("id")
    source.add_argument(
        "--kind", choices=["user_quote", "code", "document", "fixture"], required=True
    )
    source.add_argument("--summary", required=True)
    source.add_argument("--locator", required=True)
    source.add_argument("--raw-file")
    rule = commands.add_parser("propose")
    rule.add_argument("id")
    rule.add_argument("--text", required=True)
    rule.add_argument("--source", action="append", required=True)
    rule.add_argument("--risk", choices=["low", "medium", "high"], default="medium")
    rule.add_argument("--reason", required=True)
    for action in ("adopt", "retire"):
        step = commands.add_parser(action)
        step.add_argument("id")
        step.add_argument("--reason", required=True)
    accepted = commands.add_parser("confirm", help="记录确认声明，工具不验证确认人的身份")
    accepted.add_argument("id")
    accepted.add_argument("--source", required=True)
    accepted.add_argument("--revision", type=int, required=True)
    accepted.add_argument("--kind", choices=["human_explicit", "fixture_only"], required=True)
    accepted.add_argument("--note", required=True)
    accepted.add_argument("--recorded-by", required=True)
    return parser


# 项目位置来自统一dev入口，生成的新项目不会写回模板本机材料。
def main() -> None:
    run(parser().parse_args(), PROJECT)


if __name__ == "__main__":
    main()
