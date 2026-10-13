"""
开工、范围、契约变化与收工证据各自核对，跳过、旧源码、模拟和缺库不能成为完成。
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi_project.development.evidence import system_fingerprint
from fastapi_project.development.history import fingerprints
from fastapi_project.development.task_models import read_card
from fastapi_project.development.tasks import finish_task, start_task

from shared.modules.catalog import Catalog
from tests.framework.test_observation_points import module


# 最小独立样例用明确编号与标记，不把任何业务规则写进正式空模板。
def sample(project: Path) -> Catalog:
    tests = project / "server/tests/modules/sample_counts/test_sample.py"
    tests.parent.mkdir(parents=True)
    tests.write_text("def test_sample():\n    assert 9 == 9\n")
    path = project / "doc/sample_counts/cases/one.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "id": "sample_counts.R-01-C01",
                "input": {"amount": 4},
                "initial": {},
                "expected": {"total": 9},
                "assertions": ["合成数量为9"],
                "tests": ["tests/modules/sample_counts/test_sample.py::test_sample"],
            }
        )
    )
    return Catalog([module])


# 保存准确范围的当前版本，不凭登记数量或没有执行的建议命令生成成功。
def record(project: Path, catalog: Catalog, outcome="passed", *, simulated=False) -> dict:
    return {
        "id": "synthetic-check",
        "finished_at": datetime.now(UTC).isoformat(),
        "scope": {"kind": "module", "module": "sample_counts"},
        "passed": True,
        "source_changed": False,
        "fingerprints": fingerprints(project, list(catalog.modules), catalog.links()),
        "system_fingerprint": system_fingerprint(project),
        "suites": [
            {
                "database": "sqlite",
                "exit_code": 0,
                "cases": [
                    {
                        "nodeid": "tests/modules/sample_counts/test_sample.py::test_sample",
                        "scenario_ids": ["sample_counts.R-01-C01"],
                        "outcome": outcome,
                        "runs": [{"simulated": simulated}],
                    }
                ],
            }
        ],
    }


# 实际新鲜成功与范围外变更分开显示，范围清单不会悄悄消失。
def test_task_start_and_finish_with_current_evidence(tmp_path: Path) -> None:
    catalog = sample(tmp_path)
    card = start_task(tmp_path, catalog, "sample_counts", ["R-01-C01"])
    assert read_card(tmp_path, card.id).state == "active"
    outside = tmp_path / "README.md"
    outside.write_text("范围外说明变化。")
    completed = finish_task(tmp_path, catalog, card, record(tmp_path, catalog), ("sqlite",))
    assert completed.state == "complete" and completed.outside == ["README.md"]
    assert (tmp_path / ".agents/records/reviews" / (card.id + ".json")).is_file()


# 未通过或模拟的样例不能由全局passed字段掩盖。
@pytest.mark.parametrize(
    "outcome,simulated", [("skipped", False), ("failed", False), ("passed", True)]
)
def test_finish_refuses_invalid_case_evidence(
    tmp_path: Path, outcome: str, simulated: bool
) -> None:
    catalog = sample(tmp_path)
    card = start_task(tmp_path, catalog, "sample_counts", ["R-01-C01"])
    result = finish_task(
        tmp_path,
        catalog,
        card,
        record(tmp_path, catalog, outcome, simulated=simulated),
        ("sqlite",),
    )
    assert result.state == "incomplete" and result.problems


# 兄弟包的模拟轨迹不影响本包收工，同一轨迹属于本包时仍拒绝。
def test_finish_allows_sibling_simulation(tmp_path: Path) -> None:
    catalog = sample(tmp_path)
    card = start_task(tmp_path, catalog, "sample_counts", ["R-01-C01"])
    evidence = record(tmp_path, catalog)
    evidence["suites"][0]["cases"][0]["runs"] = [
        {"operation": "sample_sources.load", "simulated": True},
        {"operation": "sample_counts.run", "simulated": False},
    ]
    assert finish_task(tmp_path, catalog, card, evidence, ("sqlite",)).state == "complete"
    evidence["suites"][0]["cases"][0]["runs"][1]["simulated"] = True
    result = finish_task(tmp_path, catalog, card, evidence, ("sqlite",))
    assert result.state == "incomplete" and any("模拟" in p for p in result.problems)


# 收工失败摘要带检查名和详细原因，不让模型回翻长输出寻找原因。
def test_finish_failure_lists_check_names_and_reasons(tmp_path: Path) -> None:
    catalog = sample(tmp_path)
    card = start_task(tmp_path, catalog, "sample_counts", ["R-01-C01"])
    evidence = record(tmp_path, catalog)
    evidence.update(passed=False, checks={"生成文档": False, "规则与实现状态": False},
                    problems=["service/sample_counts：规则 R-01 未确认"])
    result = finish_task(tmp_path, catalog, card, evidence, ("sqlite",))
    assert any("生成文档" in p for p in result.problems)
    assert any("service/sample_counts" in p for p in result.problems)


# 缺库与检查结束后源码变化分别给出原因，不能拼接过去的PG结果。
def test_finish_requires_database_and_exact_source(tmp_path: Path) -> None:
    catalog = sample(tmp_path)
    card = start_task(tmp_path, catalog, "sample_counts", ["R-01-C01"])
    evidence = record(tmp_path, catalog)
    result = finish_task(tmp_path, catalog, card, evidence, ("sqlite", "postgresql"))
    assert result.state == "incomplete" and any("postgresql" in p for p in result.problems)
    test = tmp_path / "server/tests/modules/sample_counts/test_sample.py"
    test.write_text(test.read_text() + "# 本次检查后改了源码\n")
    result = finish_task(tmp_path, catalog, card, evidence, ("sqlite",))
    assert result.state == "incomplete" and any("当前源码" in p for p in result.problems)


# 未定义样例不能创建空完成条件，契约变更需要新任务资料。
def test_unknown_cases_and_contract_changes(tmp_path: Path) -> None:
    catalog = sample(tmp_path)
    with pytest.raises(ValueError, match="未定义"):
        start_task(tmp_path, catalog, "sample_counts", ["R-01-C99"])
    card = start_task(tmp_path, catalog, "sample_counts", ["R-01-C01"])
    card.contracts = "synthetic-old-contract"
    result = finish_task(tmp_path, catalog, card, record(tmp_path, catalog), ("sqlite",))
    assert result.state == "needs_update"


# 独立复核材料提供准确基线差异，不附写代码者的说明或检查结果。
def test_review_pack_is_exact_and_keeps_results_out(tmp_path: Path) -> None:
    from fastapi_project.development.task_baseline import review_pack

    catalog = sample(tmp_path)
    card = start_task(tmp_path, catalog, "sample_counts", ["R-01-C01"])
    test = tmp_path / "server/tests/modules/sample_counts/test_sample.py"
    test.write_text("def test_sample():\n    assert 8 == 8\n")
    card.checks = ["synthetic-passed-secret-check-id"]
    text = review_pack(tmp_path, card).read_text()
    assert "-    assert 9 == 9" in text and "+    assert 8 == 8" in text
    assert "synthetic-passed-secret-check-id" not in text


# 当前契约变化时视图立即显示过期，原任务卡仍保持历史状态。
def test_task_view_recomputes_contract_state_without_writes(tmp_path: Path) -> None:
    from dataclasses import replace

    from fastapi_project.development.task_views import task_status

    catalog = sample(tmp_path)
    card = start_task(tmp_path, catalog, "sample_counts", ["R-01-C01"])
    changed = replace(module, title="新用途", kind="workflow")
    tasks = task_status(tmp_path, Catalog([changed]))
    assert tasks[0]["state"] == "needs_update"
    assert read_card(tmp_path, card.id).state == "active"


# 已开始任务的实际调用发生变化，旧卡不能继续按旧依赖宣称契约未变。
def test_task_view_detects_new_dependency(tmp_path: Path, monkeypatch) -> None:
    from fastapi_project.development.task_views import task_status

    catalog = sample(tmp_path)
    card = start_task(tmp_path, catalog, "sample_counts", ["R-01-C01"])
    monkeypatch.setattr(catalog, "links", lambda: {"sample_counts": {"sample_sources": ["读取"]}})
    assert task_status(tmp_path, catalog)[0]["state"] == "needs_update"
    assert read_card(tmp_path, card.id).state == "active"
