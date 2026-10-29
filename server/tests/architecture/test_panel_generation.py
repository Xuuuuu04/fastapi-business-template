import json
from pathlib import Path

from fastapi_project.development.panel_data import panel_data
from fastapi_project.panel import embedded_json, generate, render
from fastapi_template.template.files import managed_files

from shared.modules.catalog import Catalog


def planned_project(project: Path) -> dict:
    packages = [
        {
            "module": f"sample_package{number}",
            "title": f"合成包{number}",
            "kind": "capability",
            "operations": ["run"],
            "dependencies": [f"sample_package{number - 1}"] if number else [],
        }
        for number in range(20)
    ]
    (project / "project-plan.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "name": "合成二十包面板",
                "lines": [{"name": "合成业务线", "packages": packages}],
            }
        )
    )
    return panel_data(project, Catalog([]))


def test_offline_panel_has_twenty_planned_nodes_and_safe_text(tmp_path: Path) -> None:
    data = planned_project(tmp_path)
    assert len(data["nodes"]) == 20 and len(data["edges"]) == 19
    assert all(node["state"] == "planned" for node in data["nodes"])
    data["name"] = '</script><img src=x onerror="alert(1)">'
    text = render(data)
    assert data["name"] not in text
    assert json.loads(embedded_json(data))["name"] == data["name"]
    assert 'src="https://' not in text and 'href="https://' not in text
    assert "connect-src 'none'" in text and "dagre" in text
    assert "@@" not in text
    data["name"] = "@@SCRIPT@@"
    payload = render(data).split('id="panel-data">', 1)[1].split("</script>", 1)[0]
    assert json.loads(payload)["name"] == "@@SCRIPT@@"


def test_notes_do_not_change_evidence_state(tmp_path: Path) -> None:
    before = planned_project(tmp_path)
    note = tmp_path / ".agents/records/notes/sample_package0.md"
    note.parent.mkdir(parents=True)
    note.write_text("作者声称全部通过；@@SCRIPT@@<script>alert(1)</script>")
    after = panel_data(tmp_path, Catalog([]))
    assert [node["state"] for node in before["nodes"]] == [node["state"] for node in after["nodes"]]
    assert after["nodes"][0]["note"] == note.read_text()


def test_panel_generation_preserves_source_and_empty_template(tmp_path: Path) -> None:
    planned_project(tmp_path)
    plan = (tmp_path / "project-plan.json").read_bytes()
    result = generate(tmp_path, Catalog([]))
    assert result == tmp_path / "out/panel/index.html" and result.is_file()
    assert (tmp_path / "project-plan.json").read_bytes() == plan
    assert not (tmp_path / "server/service").exists()
    assert not (tmp_path / ".agents/records/tasks").exists()


def test_panel_assets_are_managed_upgrade_files(tmp_path: Path) -> None:
    folder = tmp_path / ".agents/skills/fastapi-project/assets/panel"
    folder.mkdir(parents=True)
    for name in ("style.css", "vendor.json", "panel.js", "page.html"):
        (folder / name).write_text("合成升级资产")
    files = managed_files(tmp_path)
    assert {Path(name).name for name in files} == {
        "style.css",
        "vendor.json",
        "panel.js",
        "page.html",
    }


def test_planned_package_keeps_high_risk_unconfirmed_rules(tmp_path: Path) -> None:
    from fastapi_project.development.ledger import add_source, propose
    from fastapi_project.development.ledger_models import LedgerRule, RuleSource

    planned_project(tmp_path)
    add_source(
        tmp_path,
        RuleSource(
            id="synthetic-rule", kind="fixture", summary="合成材料", locator="fixture:planned"
        ),
    )
    propose(
        tmp_path,
        LedgerRule(
            id="sample_package0.R-01",
            text="合成高风险规则",
            sources=["synthetic-rule"],
            risk="high",
        ),
        reason="计划阶段提出",
    )
    data = panel_data(tmp_path, Catalog([]))
    node = next(node for node in data["nodes"] if node["id"] == "sample_package0")
    assert node["state"] == "planned" and node["pending_confirmation"]
    assert node["rules"][0]["id"] == "sample_package0.R-01"
