from pathlib import Path
from string import Template

import pytest
from fastapi_check.quality.files import check_files
from fastapi_check.quality.rules import ROOT
from fastapi_module.new_module import TEMPLATES, targets

from shared.modules.layout import check_layout
from shared.modules.validation.imports import check_imports


@pytest.mark.parametrize("kind", ["capability", "workflow"])
def test_new_module_templates_follow_rules(tmp_path: Path, kind: str) -> None:
    values = {"name": "order_desk", "title": "订单台", "Camel": "OrderDesk", "path": "order-desk"}
    for source, path in targets("order_desk", kind).items():
        text = Template((TEMPLATES / source).read_text(encoding="utf-8")).substitute(values)
        place = tmp_path / path.relative_to(ROOT)
        place.parent.mkdir(parents=True, exist_ok=True)
        place.write_text(text, encoding="utf-8")
        if place.suffix == ".py":
            compile(text, str(place), "exec")
    assert check_layout(tmp_path, ["order_desk"]) == []
    assert [problem.text() for problem in check_imports(tmp_path, strict=True)] == []
    rules = {"comment", "docstring", "catch"}
    assert [p.text() for p in check_files(tmp_path) if p.rule in rules] == []
