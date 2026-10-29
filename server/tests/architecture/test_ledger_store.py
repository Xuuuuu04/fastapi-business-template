import json
import signal
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi_check.quality.docs import check_development_rules
from fastapi_project.development import ledger_store
from fastapi_project.development.history import fingerprints
from fastapi_project.development.ledger import add_source, propose, read_ledger, save_ledger
from fastapi_project.development.ledger_models import LedgerRule, RuleLedger, RuleSource
from fastapi_project.development.ledger_store import recover_store

from shared.modules.catalog import Catalog
from tests.environment import subprocess_environment


def ledger() -> RuleLedger:
    return RuleLedger(
        sources=[
            RuleSource(id="synthetic", kind="fixture", summary="合成资料", locator="synthetic-only")
        ],
        rules=[
            LedgerRule(id=f"sample_{name}.R-01", text="original-rule-text", sources=["synthetic"])
            for name in ("first", "second")
        ],
    )


def test_legacy_to_package_files_preserves_rule_meaning(tmp_path: Path) -> None:
    path = tmp_path / "doc/rules-ledger.json"
    path.parent.mkdir()
    path.write_text(ledger().model_dump_json(indent=2))
    before = path.read_bytes()
    assert all(rule.state == "inferred" for rule in read_ledger(tmp_path).rules)
    assert path.read_bytes() == before
    save_ledger(tmp_path, read_ledger(tmp_path))
    assert json.loads(path.read_text())["schema_version"] == 2
    second = tmp_path / "doc/sample_second/rules.json"
    preserved = second.read_bytes()
    propose(
        tmp_path,
        LedgerRule(id="sample_first.R-01", text="new-rule-text", sources=["synthetic"]),
        reason="合成变更",
    )
    assert second.read_bytes() == preserved
    assert read_ledger(tmp_path).rules[0].revision == 2


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_package_write_failure_restores_originals(
    tmp_path: Path, monkeypatch, newline: bytes
) -> None:
    save_ledger(tmp_path, ledger())
    for path in (tmp_path / "doc").rglob("*.json"):
        path.write_bytes(path.read_bytes().replace(b"\n", newline))
    originals = {path: path.read_bytes() for path in (tmp_path / "doc").rglob("*.json")}
    real = ledger_store.atomic_bytes

    def failing(path, content):
        real(path, content)
        if path.name == "rules.json" and b"new-rule-text" in content:
            raise OSError("synthetic write failure")

    monkeypatch.setattr(ledger_store, "atomic_bytes", failing)
    with pytest.raises(OSError, match="synthetic"):
        propose(
            tmp_path,
            LedgerRule(id="sample_first.R-01", text="new-rule-text", sources=["synthetic"]),
            reason="合成变更",
        )
    assert all(path.read_bytes() == content for path, content in originals.items())
    assert not (tmp_path / ledger_store.JOURNAL).exists()


def test_interrupted_write_requires_recovery(tmp_path: Path, monkeypatch) -> None:
    save_ledger(tmp_path, ledger())
    real = ledger_store.atomic_bytes

    def interrupted(path, content):
        real(path, content)
        if path.name == "rules.json" and b"new-rule-text" in content:
            raise KeyboardInterrupt("synthetic interruption")

    monkeypatch.setattr(ledger_store, "atomic_bytes", interrupted)
    with pytest.raises(KeyboardInterrupt):
        propose(
            tmp_path,
            LedgerRule(id="sample_first.R-01", text="new-rule-text", sources=["synthetic"]),
            reason="合成变更",
        )
    assert all(rule.text == "original-rule-text" for rule in read_ledger(tmp_path).rules)
    assert any(
        problem.rule == "ledger_recovery"
        for problem in check_development_rules(Catalog([]), tmp_path, delivery=True)
    )
    monkeypatch.setattr(ledger_store, "atomic_bytes", real)
    assert recover_store(tmp_path)
    assert all(rule.text == "original-rule-text" for rule in read_ledger(tmp_path).rules)
    assert not recover_store(tmp_path)


def test_source_index_stays_separate_from_packages(tmp_path: Path) -> None:
    save_ledger(tmp_path, ledger())
    packages = {path: path.read_bytes() for path in (tmp_path / "doc").glob("*/rules.json")}
    add_source(
        tmp_path,
        RuleSource(id="extra", kind="user_quote", summary="脱敏引用", locator="local-only"),
        raw="synthetic-sensitive-original",
    )
    assert all(path.read_bytes() == content for path, content in packages.items())
    assert "synthetic-sensitive-original" not in (tmp_path / "doc/rules-ledger.json").read_text()


def test_rule_fingerprints_follow_actual_dependency_scope(tmp_path: Path) -> None:
    save_ledger(tmp_path, ledger())
    names = ["sample_first", "sample_second"]
    before = fingerprints(tmp_path, names)
    add_source(
        tmp_path, RuleSource(id="unused", kind="fixture", summary="无关合成资料", locator="unused")
    )
    assert fingerprints(tmp_path, names) == before
    dependent = {"sample_second": {"sample_first": ["合成只读引用"]}}
    linked = fingerprints(tmp_path, names, dependent)
    propose(
        tmp_path,
        LedgerRule(id="sample_first.R-01", text="new-rule-text", sources=["synthetic"]),
        reason="合成变更",
    )
    after = fingerprints(tmp_path, names)
    assert after["sample_first"] != before["sample_first"]
    assert after["sample_second"] == before["sample_second"]
    assert fingerprints(tmp_path, names, dependent)["sample_second"] != linked["sample_second"]


@pytest.mark.skipif(sys.platform == "win32", reason="此反例使用POSIX SIGKILL")
def test_sigkill_rule_writer_recovers_old_snapshot(tmp_path: Path) -> None:
    save_ledger(tmp_path, ledger())
    script = """
import os, signal, sys
from pathlib import Path
from fastapi_dev.main import bootstrap
bootstrap(Path.cwd().parent)
from fastapi_project.development import ledger_store
from fastapi_project.development.ledger import propose
from fastapi_project.development.ledger_models import LedgerRule
real = ledger_store.atomic_bytes
def kill_after_write(path, content):
    real(path, content)
    if path.name == 'rules.json' and b'new-rule-text' in content:
        os.kill(os.getpid(), signal.SIGKILL)
ledger_store.atomic_bytes = kill_after_write
rule = LedgerRule(id='sample_first.R-01', text='new-rule-text', sources=['synthetic'])
propose(Path(sys.argv[1]), rule, reason='synthetic SIGKILL')
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        env=subprocess_environment(),
        timeout=10,
        capture_output=True,
    )
    assert result.returncode == -signal.SIGKILL
    assert all(rule.text == "original-rule-text" for rule in read_ledger(tmp_path).rules)
    assert recover_store(tmp_path)
    assert all(rule.text == "original-rule-text" for rule in read_ledger(tmp_path).rules)


@pytest.mark.parametrize(
    "file,content",
    [
        ("doc/rules-ledger.json", '{"schema_version":2,"packages":9}'),
        (ledger_store.JOURNAL, '{"schema_version":1}'),
        ("doc/sample_first/rules.json", "[{}]"),
    ],
)
def test_malformed_store_metadata_rejected(tmp_path: Path, file: str, content: str) -> None:
    from fastapi_project.panel import generate

    save_ledger(tmp_path, ledger())
    path = tmp_path / file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    output = tmp_path / "out/panel/index.html"
    output.parent.mkdir(parents=True)
    output.write_text("old-green-result")
    with pytest.raises(ValueError):
        generate(tmp_path, Catalog([]))
    assert "old-green-result" not in output.read_text()
    assert "证据无法读取" in output.read_text()
