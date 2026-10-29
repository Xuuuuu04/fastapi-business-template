from pathlib import Path

import pytest
from fastapi_check.quality.rules import PROJECT
from fastapi_template.template.initialization import initialize


def test_initialization_rejects_existing_directory(tmp_path: Path) -> None:
    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "owned.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError):
        initialize(PROJECT, existing, "产品")
    assert (existing / "owned.txt").read_text() == "keep"
    with pytest.raises(ValueError):
        initialize(PROJECT, PROJECT / "nested-product", "产品")


def test_new_product_keeps_business_entry(tmp_path: Path) -> None:
    target = tmp_path / "shop"
    initialize(PROJECT, target, "门店系统")
    agents = (target / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.startswith("# 门店系统\n\n## 业务要点\n")
    business = target / ".agents/skills/fastapi-business/business.md"
    assert "已对照到提交：无" in business.read_text(encoding="utf-8")
    assert not (target / ".agents/TASK.md").exists()
