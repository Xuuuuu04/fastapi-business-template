"""
计划及入口的一致性：已实现名称失效报具体项，生成段保留手写文字，汇总只生成不比较。
"""

import json
from pathlib import Path

from fastapi_docs.entry_state import block, render, stale
from fastapi_project.development.plan_entries import capture, check_entries

from shared.modules.catalog import Catalog
from tests.framework.pipeline_sample import module


# 共用最小计划，未实现操作合法保留，不因无登记而错报。
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


# 导出捕获已实现操作，名字改错后明确报到JSON操作位置。
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


# 未迁移的旧流程文档也能证明实现过，不需要代理靠记忆指出旧名。
def test_legacy_flow_proves_old_operation(tmp_path: Path) -> None:
    folder = tmp_path / "doc/pipeline_sample"
    folder.mkdir(parents=True)
    (folder / "flows.md").write_text("## 来源选择（pipeline_sample.choose）\n")
    problems = check_entries(Catalog([]), tmp_path, plan())
    assert len(problems) == 1 and "pipeline_sample.choose" in problems[0]


# 生成段每模块一行，保留手写部分；只改登记或关闭配置才要求更新。
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


# 派生账本变化不成为手写业务标题，第一次导出后入口不能立即过期。
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


# 大项目全局文本摘要仍在一屏内，细节命令与省略总数可见。
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
