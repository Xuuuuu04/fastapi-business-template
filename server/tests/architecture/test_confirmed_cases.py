"""
确认样例保护独立预期与关键断言，允许修改辅助代码；Git基线防止重算摘要掩盖变更。
"""

import json
import subprocess
from pathlib import Path

import pytest
from fastapi_project.development.confirmed_cases import case_problems, rule_cases
from fastapi_project.development.ledger import (
    add_source,
    confirm,
    propose,
    read_ledger,
    save_ledger,
    transition,
)
from fastapi_project.development.ledger_models import LedgerRule, RuleConfirmation, RuleSource


# 合成项目独立资料，不把任何规则登记到正式空模板中。
def prepare(project: Path) -> Path:
    tests = project / "server/tests/modules/sample_rules/test_sample.py"
    tests.parent.mkdir(parents=True)
    tests.write_text("def test_sample():\n    value = 4\n    assert value == 4\n")
    path = project / "doc/sample_rules/cases/one.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "id": "sample_rules.R-01-C01",
                "input": {"amount": 2},
                "initial": {"rows": []},
                "expected": {"total": 4},
                "database": {"count": 1},
                "effects": {"sends": 0},
                "assertions": ["得到两倍数量，保存一行，不发送"],
                "tests": ["tests/modules/sample_rules/test_sample.py::test_sample"],
            }
        )
    )
    add_source(
        project,
        RuleSource(
            id="source-one",
            kind="user_quote",
            summary="合成原话",
            locator="fixture:one",
        ),
    )
    rule = LedgerRule(id="sample_rules.R-01", text="合成规则", sources=["source-one"], risk="high")
    propose(project, rule, reason="合成推定")
    transition(project, rule.id, "adopted", reason="合成采纳")
    confirm(
        project,
        rule.id,
        RuleConfirmation(
            source="source-one",
            revision=1,
            kind="human_explicit",
            note="合成确认",
            recorded_by="synthetic",
            recorded_at="2026-10-12T00:00:00Z",
        ),
    )
    return path


# 保护每种关键语义，改测试辅助变量不等于改关键断言。
@pytest.mark.parametrize("field", ["input", "initial", "expected", "database", "effects"])
def test_confirmed_fixture_change_is_detected(tmp_path: Path, field: str) -> None:
    path = prepare(tmp_path)
    assert not case_problems(tmp_path, read_ledger(tmp_path), delivery=True)
    payload = json.loads(path.read_text())
    payload[field]["changed"] = True
    path.write_text(json.dumps(payload))
    assert "已经改变" in case_problems(tmp_path, read_ledger(tmp_path))[0]


# 锁关键assert表达式，注释和无关辅助函数的修改仍可接受。
def test_assertions_protected_without_locking_file(tmp_path: Path) -> None:
    prepare(tmp_path)
    test = tmp_path / "server/tests/modules/sample_rules/test_sample.py"
    test.write_text(test.read_text() + "\n# 新辅助说明\ndef helper():\n    return 1\n")
    assert not case_problems(tmp_path, read_ledger(tmp_path))
    test.write_text(test.read_text().replace("assert value == 4", "assert value == 5"))
    assert case_problems(tmp_path, read_ledger(tmp_path))


# 在版本历史里保存独立确认基线，当前JSON改摘要也不能使变更变绿。
def test_recomputed_digest_cannot_replace_git_confirmation(tmp_path: Path) -> None:
    path = prepare(tmp_path)
    for command in (
        ["init", "-q"],
        ["add", "."],
        [
            "-c",
            "user.name=Synthetic",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "confirmed synthetic case",
        ],
    ):
        subprocess.run(["git", *command], cwd=tmp_path, check=True, capture_output=True)
    payload = json.loads(path.read_text())
    payload["expected"]["total"] = 5
    path.write_text(json.dumps(payload))
    ledger = read_ledger(tmp_path)
    ledger.rules[0] = ledger.rules[0].model_copy(
        update={
            "case_digests": rule_cases(tmp_path, ledger.rules[0].id),
        }
    )
    save_ledger(tmp_path, ledger)
    assert any("缺少新修订依据" in error for error in case_problems(tmp_path, ledger))
    ledger.rules.clear()
    assert any("被删除" in error for error in case_problems(tmp_path, ledger))


# 高风险未确认规则只在交付时失败，普通开发可以继续试验。
def test_delivery_requires_high_risk_confirmation(tmp_path: Path) -> None:
    prepare(tmp_path)
    ledger = read_ledger(tmp_path)
    propose(tmp_path, ledger.rules[0].model_copy(update={"text": "新推定"}), reason="合成变更")
    assert not case_problems(tmp_path, read_ledger(tmp_path))
    assert any(
        "尚未明确确认" in e for e in case_problems(tmp_path, read_ledger(tmp_path), delivery=True)
    )


# 参数化或局部预期变量变化不能只靠保持assert语句原样而绕过保护。
def test_assertion_inputs_cannot_be_changed(tmp_path: Path) -> None:
    prepare(tmp_path)
    test = tmp_path / "server/tests/modules/sample_rules/test_sample.py"
    test.write_text(test.read_text().replace("value = 4", "value = 5"))
    assert case_problems(tmp_path, read_ledger(tmp_path))


# 确认单只读独立样例，新的原话修订恢复推定，不复制旧确认。
def test_sheet_and_supersede_keep_confirmation_separate(tmp_path: Path) -> None:
    from fastapi_project.development.rule_documents import confirm_sheet, supersede

    prepare(tmp_path)
    add_source(
        tmp_path,
        RuleSource(
            id="source-two",
            kind="user_quote",
            summary="第二份合成原话",
            locator="fixture:two",
        ),
    )
    with pytest.raises(ValueError, match="新的原话"):
        supersede(tmp_path, "sample_rules.R-01", "新规则", "source-one", "合成修订")
    revised = supersede(tmp_path, "sample_rules.R-01", "新规则", "source-two", "合成修订")
    assert revised.state == "inferred" and revised.revision == 2 and not revised.case_digests
    sheet = confirm_sheet(tmp_path)
    assert "sample_rules.R-01-C01" in sheet and "{'total': 4}" in sheet


# 历史文档不能变成人类确认；格式无法解析时不新增半份来源。
def test_markdown_adoption_does_not_confirm_or_partially_parse(tmp_path: Path) -> None:
    from fastapi_project.development.rule_documents import adopt_markdown

    folder = tmp_path / "doc/sample_rules"
    folder.mkdir(parents=True)
    document = folder / "rules.md"
    document.write_text("# 合成原文\n正文缺少规则标题\n")
    with pytest.raises(ValueError, match="可解析"):
        adopt_markdown(tmp_path, "sample_rules")
    assert not read_ledger(tmp_path).sources
    document.write_text("# 合成规则\n\n### R-01 数量\n\n数量加倍。\n")
    assert adopt_markdown(tmp_path, "sample_rules") == ["sample_rules.R-01"]
    ledger = read_ledger(tmp_path)
    assert ledger.rules[0].state == "adopted" and not ledger.rules[0].confirmations
