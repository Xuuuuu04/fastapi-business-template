"""
规则账本的原子存储与生命周期操作；原始敏感材料默认不进入可提交规则文件。
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi_project.development.check_assets import atomic_bytes
from fastapi_project.development.ledger_lock import serialized
from fastapi_project.development.ledger_models import (
    LedgerRule,
    RuleConfirmation,
    RuleEvent,
    RuleLedger,
    RuleSource,
)


# 读取不到账本表示未建立，不能从代码自动生成已确认规则。
def read_ledger(project: Path) -> RuleLedger:
    path = project / "doc/rules-ledger.json"
    if not path.exists():
        return RuleLedger()
    ledger = RuleLedger.model_validate_json(path.read_bytes())
    ledger.validate_links()
    return ledger


# 一次替换整个小账本，索引坏了可以从文件和版本历史恢复。
@serialized
def save_ledger(project: Path, ledger: RuleLedger) -> Path:
    ledger.validate_links()
    path = project / "doc/rules-ledger.json"
    atomic_bytes(path, (ledger.model_dump_json(indent=2) + "\n").encode())
    return path


# 每次规则动作保存快照和原因，不只保存一个会变的摘要。
def record(ledger: RuleLedger, rule: LedgerRule, action: str, reason: str) -> None:
    ledger.events.append(
        RuleEvent(
            rule=rule.id,
            revision=rule.revision,
            action=action,
            reason=reason,
            recorded_at=datetime.now(UTC).isoformat(),
            snapshot=rule.model_dump(mode="json"),
        )
    )


# 原文仅保存在本机忽略目录，引用只提交脱敏摘要和内容指纹。
@serialized
def add_source(project: Path, source: RuleSource, *, raw: str | None = None) -> RuleSource:
    ledger = read_ledger(project)
    if any(existing.id == source.id for existing in ledger.sources):
        raise ValueError("来源编号已经存在，请为新材料生成新编号")
    if raw is not None:
        digest = hashlib.sha256(raw.encode()).hexdigest()
        source = source.model_copy(update={"raw_digest": digest})
        path = project / ".agents/records/business-raw" / (source.id + ".txt")
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_bytes(path, raw.encode())
        path.chmod(0o600)
    ledger.sources.append(source)
    save_ledger(project, ledger)
    return source


# 修订确认规则会恢复为推定，新文本必须重新经过采纳与确认，旧确认留在历史。
@serialized
def propose(project: Path, rule: LedgerRule, *, reason: str) -> LedgerRule:
    ledger = read_ledger(project)
    previous = next((item for item in ledger.rules if item.id == rule.id), None)
    if previous:
        rule = rule.model_copy(
            update={
                "revision": previous.revision + 1,
                "state": "inferred",
                "confirmations": [],
                "case_digests": {},
            }
        )
        ledger.rules = [item for item in ledger.rules if item.id != rule.id]
    elif rule.state != "inferred" or rule.revision != 1 or rule.confirmations:
        raise ValueError("新规则先作为推定登记，不允许导入时自动确认")
    ledger.rules.append(rule)
    record(ledger, rule, "propose", reason)
    save_ledger(project, ledger)
    return rule


# 采纳与废止保留来源，废止不能被误解释为没有需求。
@serialized
def transition(
    project: Path, id: str, state: Literal["adopted", "retired"], *, reason: str
) -> LedgerRule:
    ledger = read_ledger(project)
    previous = next(item for item in ledger.rules if item.id == id)
    if previous.state == "retired":
        raise ValueError("废止规则需要新修订，不能直接复活旧确认")
    rule = previous.model_copy(update={"state": state})
    ledger.rules = [rule if item.id == id else item for item in ledger.rules]
    record(ledger, rule, state, reason)
    save_ledger(project, ledger)
    return rule


# 明确确认记录是人类确认声明，不声称记录者身份已被摘要或工具验证。
@serialized
def confirm(project: Path, id: str, confirmation: RuleConfirmation) -> LedgerRule:
    from fastapi_project.development.confirmed_cases import rule_cases

    ledger = read_ledger(project)
    previous = next(item for item in ledger.rules if item.id == id)
    if previous.state not in {"adopted", "confirmed"} or confirmation.revision != previous.revision:
        raise ValueError("先采纳当前修订，确认不能用于另一版规则")
    if confirmation.kind == "fixture_only":
        state = previous.state
    else:
        state = "confirmed"
    rule = previous.model_copy(
        update={
            "state": state,
            "confirmations": [*previous.confirmations, confirmation],
            "case_digests": (
                rule_cases(project, id)
                if confirmation.kind == "human_explicit"
                else previous.case_digests
            ),
        }
    )
    ledger.rules = [rule if item.id == id else item for item in ledger.rules]
    record(ledger, rule, "confirm", confirmation.note)
    save_ledger(project, ledger)
    return rule


# 内容摘要用于检查过期，不证明确认人的身份。
def ledger_digest(ledger: RuleLedger) -> str:
    body = json.dumps(ledger.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()
