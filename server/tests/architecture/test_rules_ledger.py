from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi_project.development.ledger import add_source, confirm, propose, read_ledger, transition
from fastapi_project.development.ledger_models import LedgerRule, RuleConfirmation, RuleSource


def source(project: Path, kind="user_quote") -> None:
    add_source(
        project,
        RuleSource(
            id="source-one", kind=kind, summary="合成脱敏摘要", locator="fixture:source-one"
        ),
    )


def test_rule_lifecycle_keeps_history(tmp_path: Path) -> None:
    source(tmp_path)
    rule = LedgerRule(id="sample_rules.R-01", text="合成规则", sources=["source-one"])
    propose(tmp_path, rule, reason="依据合成原话推定")
    transition(tmp_path, rule.id, "adopted", reason="合成采纳")
    accepted = confirm(
        tmp_path,
        rule.id,
        RuleConfirmation(
            source="source-one",
            revision=1,
            kind="human_explicit",
            note="合成确认声明，非真实用户规则",
            recorded_by="synthetic-human-record",
            recorded_at="2026-10-12T00:00:00Z",
        ),
    )
    assert accepted.state == "confirmed"
    revised = propose(
        tmp_path, rule.model_copy(update={"text": "合成新规则"}), reason="合成变更依据"
    )
    assert revised.revision == 2 and revised.state == "inferred" and not revised.confirmations
    ledger = read_ledger(tmp_path)
    assert len(ledger.events) == 4
    assert ledger.events[2].snapshot["state"] == "confirmed"
    assert ledger.events[2].snapshot["text"] == "合成规则"


@pytest.mark.parametrize("kind", ["code", "document", "fixture"])
def test_imported_sources_cannot_be_human_confirmation(tmp_path: Path, kind: str) -> None:
    source(tmp_path, kind)
    rule = LedgerRule(id="sample_rules.R-01", text="合成历史规则", sources=["source-one"])
    propose(tmp_path, rule, reason="合成导入")
    transition(tmp_path, rule.id, "adopted", reason="合成采纳")
    with pytest.raises(ValueError, match="人类确认"):
        confirm(
            tmp_path,
            rule.id,
            RuleConfirmation(
                source="source-one",
                revision=1,
                kind="human_explicit",
                note="试图从历史直接确认",
                recorded_by="test",
                recorded_at="2026-10-12T00:00:00Z",
            ),
        )
    assert read_ledger(tmp_path).rules[0].state == "adopted"


def test_raw_material_stays_outside_ledger(tmp_path: Path) -> None:
    raw = "synthetic-private-original-do-not-publish"
    saved = add_source(
        tmp_path,
        RuleSource(
            id="private-one", kind="user_quote", summary="脱敏合成摘要", locator="local:private-one"
        ),
        raw=raw,
    )
    document = (tmp_path / "doc/rules-ledger.json").read_text()
    assert raw not in document and saved.raw_digest
    material = tmp_path / ".agents/records/business-raw/private-one.txt"
    assert material.read_text() == raw and material.stat().st_mode & 0o777 == 0o600


def test_retired_rule_requires_new_revision(tmp_path: Path) -> None:
    source(tmp_path)
    rule = LedgerRule(id="sample_rules.R-01", text="合成规则", sources=["source-one"])
    propose(tmp_path, rule, reason="合成推定")
    transition(tmp_path, rule.id, "retired", reason="合成废止")
    with pytest.raises(ValueError, match="复活"):
        transition(tmp_path, rule.id, "adopted", reason="错误复活")


def test_concurrent_sources_preserve_all_records(tmp_path: Path) -> None:
    def add(index: int) -> None:
        add_source(
            tmp_path,
            RuleSource(
                id=f"source-{index}", kind="fixture", summary="合成来源", locator=f"fixture:{index}"
            ),
        )

    with ThreadPoolExecutor(max_workers=4) as workers:
        list(workers.map(add, range(12)))
    ledger = read_ledger(tmp_path)
    assert len(ledger.sources) == 12
    lock = tmp_path / ".agents/records/rules-write-lock.sqlite3"
    lock.unlink()
    assert len(read_ledger(tmp_path).sources) == 12
