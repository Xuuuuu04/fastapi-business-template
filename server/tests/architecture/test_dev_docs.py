import json
from pathlib import Path

from fastapi import FastAPI
from fastapi_docs.api_doc import docs_app
from fastapi_docs.flow_doc import route_map
from fastapi_docs.progress_doc import RULE_HEADING, progress_doc
from fastapi_project.impact import Repo, belongs, framework_part, report, section_changes, sections

from app.setup.catalog import MODULES as PROJECT_MODULES
from shared.modules.catalog import Catalog
from tests.architecture.sample_catalog import MODULES
from tests.framework.sample_routes import sample_router

RULES = """# 示例：规则

### R-01 第一条

已确认。

### R-02 第二条

折扣比例待确认：由财务决定。
"""


def test_route_map_reads_real_routes() -> None:
    actual = route_map(docs_app())
    declared = {contract.name for contract in Catalog(PROJECT_MODULES).bindings}
    assert set(actual).issubset(declared)
    assert "sample_calc.calc" not in actual
    app = FastAPI()
    app.include_router(sample_router)
    assert route_map(app)["sample_calc.calc"] == ["POST /test/calc"]


def test_progress_counts(tmp_path: Path) -> None:
    catalog = Catalog([module for module in MODULES if module.name == "sample_records"])
    doc = tmp_path / "doc" / "sample_records"
    doc.mkdir(parents=True)
    (doc / "rules.md").write_text(RULES, encoding="utf-8")
    tests = tmp_path / "server" / "tests" / "modules" / "sample_records"
    tests.mkdir(parents=True)
    (tests / "test_rules.py").write_text("# R-01：第一条\n", encoding="utf-8")
    (tmp_path / "doc" / "tasks.md").write_text("- [ ] 甲\n- [x] 乙\n- [ ] 丙\n", encoding="utf-8")
    text = progress_doc(catalog, tmp_path)
    assert "未完成 2 项，已完成 1 项" in text
    assert "| sample_records | 记录样例 | 5 | 2 | 1/2 | 1 |" in text
    assert (
        "| sample_records | R-02 | 折扣比例待确认：由财务决定。 | doc/sample_records/rules.md:9 |"
        in text
    )
    assert "| sample_records | R-02 | 第二条 |" in text


def test_rule_section_changes() -> None:
    before = sections(RULES, RULE_HEADING)
    after = sections(
        RULES.replace("已确认。", "已确认，有变化。") + "\n### R-03 第三条\n", RULE_HEADING
    )
    assert section_changes(before, after) == ["新增 R-03", "修改 R-01"]
    appended = sections(RULES + "\n## 流程\n\n图\n", RULE_HEADING)
    assert section_changes(before, appended) == []


def test_module_and_framework_classification() -> None:
    assert belongs("server/app/api/v1/sample_records.py", "sample_records")
    assert belongs("doc/sample_records/rules.md", "sample_records")
    assert not belongs("doc/sample_records_extra/rules.md", "sample_records")
    found = framework_part(["server/shared/db/access.py", "doc/tasks.md"])
    assert found[-1] == "- `server/shared/db/access.py`" and len(found) == 3


def test_impact_report(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    write(tmp_path / "doc/sample_records/rules.md", RULES)
    api = {"paths": {"/a": {"get": {}}, "/b": {"get": {}}}}
    write(tmp_path / "doc/api/openapi.json", json.dumps(api))
    for args in (["init", "-q", "-b", "main"], ["add", "-A"]):
        repo.git(*args)
    repo.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "基准")
    changed = RULES.replace("已确认。", "改为待确认。")
    write(tmp_path / "doc/sample_records/rules.md", changed)
    write(tmp_path / "doc/api/openapi.json", json.dumps({"paths": {"/a": {"get": {}}}}))
    write(tmp_path / "server/shared/db/access.py", "")
    text = report("main", ["sample_records"], repo)
    assert "- `server/shared/db/access.py`" in text
    assert "| sample_records | 业务文档 |" in text
    assert "修改 R-01；待确认 1 → 2 处" in text
    assert "- 删除接口：GET /b" in text


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
