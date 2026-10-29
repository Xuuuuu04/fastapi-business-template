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
