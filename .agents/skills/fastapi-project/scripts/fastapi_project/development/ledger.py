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
from fastapi_project.development.ledger_store import read_store, write_store


def read_ledger(project: Path) -> RuleLedger:
    return read_store(project)


@serialized
def save_ledger(project: Path, ledger: RuleLedger) -> Path:
    return write_store(project, ledger)


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


def ledger_digest(ledger: RuleLedger) -> str:
    body = json.dumps(ledger.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()


def scoped_digest(ledger: RuleLedger, names: list[str]) -> str:
    rules = [rule for rule in ledger.rules if rule.id.split(".")[0] in names]
    sources = {name for rule in rules for name in rule.sources}
    selected = RuleLedger(
        sources=[source for source in ledger.sources if source.id in sources],
        rules=rules,
        events=[event for event in ledger.events if event.rule.split(".")[0] in names],
    )
    return ledger_digest(selected)
