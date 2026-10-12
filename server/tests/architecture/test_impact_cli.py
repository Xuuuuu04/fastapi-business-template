"""
影响报告的命令入口只展示明确的关闭状态，不从环境借用真实配置。
"""

import json

import pytest
from fastapi_project.impact import Repo, main

from shared.modules.catalog import Catalog
from tests.architecture.test_impact import catalog as catalog
from tests.architecture.test_impact import repo as repo
from tests.architecture.test_impact import write


# CLI JSON 始终使用完整 MODULES，不通过 enabled_modules 裁剪声明图。
def test_cli_json_respects_disabled_only_for_display(
    repo: Repo,
    catalog: Catalog,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write(repo.root / "server/service/gamma/public.py", "AFTER = 2\n")
    monkeypatch.setattr(
        "fastapi_project.impact.application_modules", lambda: tuple(catalog.modules.values())
    )
    monkeypatch.setattr("fastapi_project.impact.Repo", lambda: repo)
    monkeypatch.setenv("APP_DISABLED_MODULES", '["beta"]')
    monkeypatch.setattr(
        "sys.argv",
        ["fastapi_project.impact", "--base", "main", "--json", "--disabled-module", "beta"],
    )
    main()
    data = json.loads(capsys.readouterr().out)
    assert data["direct"] == ["gamma"] and data["dependents"] == ["alpha", "background", "beta"]
    assert "beta" not in data["enabled"] and "beta" in data["affected"]
