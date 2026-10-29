import json
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi_docs.entry_state import block, render, stale
from fastapi_project.development.plan_entries import capture, check_entries

from shared.modules.catalog import Catalog
from tests.framework.pipeline_sample import module


def plan():
    return {
        "schema_version": 1,
        "name": "独立入口样例",
        "lines": [
            {
                "name": "样例链",
                "packages": [
                    {
                        "module": "pipeline_sample",
                        "title": "流程样例",
                        "operations": ["choose", "not_implemented"],
                    }
                ],
            }
        ],
    }


def test_plan_records_implemented_and_rejects_missing(tmp_path: Path) -> None:
    catalog = Catalog([module])
    value = plan()
    assert check_entries(catalog, tmp_path, value) == []
    assert capture(catalog, tmp_path, value)
    assert value["lines"][0]["packages"][0]["implemented_operations"] == ["choose"]
    assert check_entries(Catalog([]), tmp_path, value)[0].startswith(
        "project-plan.json $.lines[0].packages[0].operations[0]"
    )
    assert "已删除或改名" in check_entries(Catalog([]), tmp_path, value)[0]
    saved = json.loads((tmp_path / "project-plan.json").read_text())
    assert saved == value


def test_legacy_flow_proves_old_operation(tmp_path: Path) -> None:
    folder = tmp_path / "doc/pipeline_sample"
    folder.mkdir(parents=True)
    (folder / "flows.md").write_text("## 来源选择（pipeline_sample.choose）\n")
    problems = check_entries(Catalog([]), tmp_path, plan())
    assert len(problems) == 1 and "pipeline_sample.choose" in problems[0]


def test_agents_current_state_generation(tmp_path: Path) -> None:
    catalog = Catalog([module])
    path = tmp_path / "AGENTS.md"
    path.write_text("# 我的产品\n\n手写判断：保留。\n")
    current = render(catalog, tmp_path, set())
    assert (
        "手写判断：保留。" in current
        and "对外 5 个操作、1 个定时入口、1 个多阶段流程；启用" in current
    )
    path.write_text(current)
    assert not stale(catalog, tmp_path, set())
    assert stale(catalog, tmp_path, {"pipeline_sample"})
    assert "已关闭" in block(catalog, tmp_path, {"pipeline_sample"})
    assert render(catalog, tmp_path, set()) == current


def test_generated_ledger_changes_do_not_expire_entry(tmp_path: Path) -> None:
    from fastapi_project.development.ledger_sections import section

    catalog = Catalog([module])
    path = tmp_path / "AGENTS.md"
    path.write_text("# 我的产品\n")
    current = render(catalog, tmp_path, set())
    path.write_text(current)
    changes = tmp_path / "doc/pipeline_sample/changes.md"
    changes.parent.mkdir(parents=True)
    changes.write_text(section(changes, "changes", "## 账本修订\n\n- 合成修订事件"))
    assert not stale(catalog, tmp_path, set())
    changes.write_text("## 产品实际调整\n\n" + changes.read_text())
    assert stale(catalog, tmp_path, set())


def test_agents_large_registry_and_broken_bounds(tmp_path: Path) -> None:
    catalog = Catalog(
        [
            replace(
                module,
                name=f"sample_package{number}",
                provides={},
                pipelines=(),
                jobs=(),
                schedules=(),
            )
            for number in range(20)
        ]
    )
    text = block(catalog, tmp_path, set())
    assert "另有 17 个登记项" in text and len(text.splitlines()) <= 14
    path = tmp_path / "AGENTS.md"
    path.write_text("手写判断\n<!-- fastapi-current-state:begin -->\n缺少结束边界")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="边界损坏"):
        render(catalog, tmp_path, set())
    assert path.read_bytes() == before


def test_global_summary_is_one_screen() -> None:
    from fastapi_project.development.screen_summary import render

    modules = {
        str(i): dict(
            name=f"module_{i}",
            title="职责",
            enabled=True,
            operation_count=30,
            pending=[],
            tests={"latest": {}},
        )
        for i in range(50)
    }
    summary = dict(name="大项目", modules=modules, pipelines=[], lines=[], attention=[])
    text = render(summary)
    assert len(text.splitlines()) <= 28 and "另外还有 38 个模块" in text and "--module" in text
