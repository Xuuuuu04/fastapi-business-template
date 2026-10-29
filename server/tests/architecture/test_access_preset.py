from pathlib import Path
from string import Template

from fastapi_check.quality.files import check_files
from fastapi_check.quality.rules import ROOT
from fastapi_module.access_preset import preset_targets

from shared.modules.layout import check_layout
from shared.modules.validation.imports import check_imports


def render(target: Path) -> list[Path]:
    values = {
        "name": "user_access",
        "title": "账号登录",
        "Camel": "UserAccess",
        "revision": "a1b2c3d4e5f6",
        "down_revision": "None",
        "previous": "无",
    }
    written = []
    for source, path in preset_targets("user_access", "a1b2c3d4e5f6").items():
        text = Template(source.read_text(encoding="utf-8")).substitute(values)
        place = target / path.relative_to(ROOT)
        place.parent.mkdir(parents=True, exist_ok=True)
        place.write_text(text, encoding="utf-8")
        written.append(place)
    return written


def test_account_preset_follows_business_rules(tmp_path: Path) -> None:
    written = render(tmp_path)
    for path in written:
        if path.suffix == ".py":
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
    assert check_layout(tmp_path, ["user_access"]) == []
    assert [problem.text() for problem in check_imports(tmp_path, strict=True)] == []
    rules = {"comment", "docstring", "catch"}
    assert [p.text() for p in check_files(tmp_path) if p.rule in rules] == []
