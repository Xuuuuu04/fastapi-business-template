"""
面板生成保留空模板与计划节点，离线资源和文本转义不依赖业务服务。
"""

import json
from pathlib import Path

from fastapi_project.development.panel_data import panel_data
from fastapi_project.panel import embedded_json, generate, render
from fastapi_template.template.files import managed_files

from shared.modules.catalog import Catalog


# 二十个尚未开发的包形成计划链，不能从计划声明伪造实现或测试成功。
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


# 单HTML包含布局脚本，没有外部资源地址，标题中的脚本终止符只作为数据。
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


# 备注只写文字，不能通过标题或备注中的完成声明改变实际计划状态。
def test_notes_do_not_change_evidence_state(tmp_path: Path) -> None:
    before = planned_project(tmp_path)
    note = tmp_path / ".agents/records/notes/sample_package0.md"
    note.parent.mkdir(parents=True)
    note.write_text("作者声称全部通过；@@SCRIPT@@<script>alert(1)</script>")
    after = panel_data(tmp_path, Catalog([]))
    assert [node["state"] for node in before["nodes"]] == [node["state"] for node in after["nodes"]]
    assert after["nodes"][0]["note"] == note.read_text()


# 实际生成只写派生页面，计划与规则不改，没有数据库或原话目录也能完成。
def test_panel_generation_preserves_source_and_empty_template(tmp_path: Path) -> None:
    planned_project(tmp_path)
    plan = (tmp_path / "project-plan.json").read_bytes()
    result = generate(tmp_path, Catalog([]))
    assert result == tmp_path / "out/panel/index.html" and result.is_file()
    assert (tmp_path / "project-plan.json").read_bytes() == plan
    assert not (tmp_path / "server/service").exists()
    assert not (tmp_path / ".agents/records/tasks").exists()


# 离线样式和供应商摘要进入三方升级范围，旧项目不能只得到新Python而缺页面资产。
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
