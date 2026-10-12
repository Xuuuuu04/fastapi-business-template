"""
词表显式定义优先定位，重复词义失败；规则账本生成文档不覆盖旧手写规则。
"""

from pathlib import Path

import pytest
from fastapi_project.development.glossary import BusinessTerm, add_term, match_terms
from fastapi_project.development.ledger_docs import ledger_documents
from fastapi_project.development.locate import locate

from shared.modules.catalog import Catalog
from tests.architecture.test_confirmed_cases import prepare
from tests.framework.test_observation_points import module


# 别名即使不出现在源码中，也能定位到词表明确登记的操作。
def test_glossary_locates_explicit_owner(tmp_path: Path) -> None:
    add_term(
        tmp_path,
        BusinessTerm(
            word="合成词义",
            definition="用于测试的明确计算含义",
            aliases=["别称"],
            module="sample_counts",
            operations=["sample_counts.run"],
        ),
    )
    found = locate(Catalog([module]), tmp_path, "别称")
    assert found["glossary"]["items"][0]["definition"] == "用于测试的明确计算含义"
    assert found["results"][0]["operation"] == "sample_counts.run"
    assert not found["database_read"] and len(match_terms(tmp_path, "合成词义")) == 1


# 同词、别名重叠与跨包归属都要显式整理，不能最后写入者覆盖前者。
def test_duplicate_glossary_is_not_overwritten(tmp_path: Path) -> None:
    term = BusinessTerm(
        word="数量", definition="合成数量", module="sample_counts", operations=["sample_counts.run"]
    )
    add_term(tmp_path, term)
    with pytest.raises(ValueError, match="重复"):
        add_term(tmp_path, term.model_copy(update={"module": "other_counts"}))
    with pytest.raises(ValueError, match="负责包"):
        add_term(tmp_path, term.model_copy(update={"word": "另一词", "operations": ["other.run"]}))
    assert len(match_terms(tmp_path, "数量")) == 1


# 生成账本文档包含修订与保护状态，保持人工规则文档原样兼容。
def test_rule_ledger_documents_keep_manual_history(tmp_path: Path) -> None:
    prepare(tmp_path)
    original = tmp_path / "doc/sample_rules/rules.md"
    original.write_text("历史手写规则。")
    documents = ledger_documents(tmp_path)
    content = documents[tmp_path / "doc/sample_rules/ledger.md"]
    assert "明确确认" in content and "sample_rules.R-01-C01" in content
    assert "修订历史" in content and "source-one" in content
    assert original.read_text() == "历史手写规则。"
    assert documents[original].startswith("历史手写规则。\n\n")
    original.write_text(documents[original])
    assert ledger_documents(tmp_path)[original] == documents[original]
    changes = tmp_path / "doc/sample_rules/changes.md"
    assert "账本修订" in documents[changes] and "source-one" in content
    assert not ledger_documents(tmp_path / "empty")


# 生成边界被截断时不覆盖规则原件，未采纳的历史文字也不能凭生成文档成为确认。
def test_damaged_ledger_section_preserves_manual_rules(tmp_path: Path) -> None:
    prepare(tmp_path)
    original = tmp_path / "doc/sample_rules/rules.md"
    original.write_text("手写规则\n<!-- fastapi-ledger-rules:begin -->\n未结束的生成段")
    before = original.read_bytes()
    with pytest.raises(ValueError, match="边界损坏"):
        ledger_documents(tmp_path)
    assert original.read_bytes() == before
