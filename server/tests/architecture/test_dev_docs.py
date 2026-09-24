"""
开发期观察用的生成文档和命令：接口路径从路由读取、开发进度的统计、改动影响报告的分段比较。
只使用保留的通用模块和临时目录，不依赖可删除的示例业务。
"""

import json
from pathlib import Path

from app.setup.catalog import MODULES
from shared.modules.catalog import Catalog
from tools.api_doc import docs_app
from tools.flow_doc import route_map
from tools.impact import Repo, belongs, framework_part, report, section_changes, sections
from tools.progress_doc import RULE_HEADING, progress_doc

RULES = """# 示例：规则

### R-01 第一条

已确认。

### R-02 第二条

折扣比例待确认：由财务决定。
"""


# 接口路径按接口函数实际引用的操作得出；一个操作可以对应多个接口，定时任务不经接口。
def test_route_map_reads_real_routes() -> None:
    routes = route_map(docs_app())
    assert routes["user_access.login"] == ["POST /api/v1/access/login"]
    assert len(routes["file_library.get_file"]) == 2
    assert "file_library.clean_files" not in routes


# 进度文档统计规则、测试标注、待确认和任务数，并列出没有测试标注的规则。
def test_progress_counts(tmp_path: Path) -> None:
    catalog = Catalog([module for module in MODULES if module.name == "file_library"])
    doc = tmp_path / "doc" / "file_library"
    doc.mkdir(parents=True)
    (doc / "rules.md").write_text(RULES, encoding="utf-8")
    tests = tmp_path / "server" / "tests" / "modules" / "file_library"
    tests.mkdir(parents=True)
    (tests / "test_rules.py").write_text("# R-01：第一条\n", encoding="utf-8")
    (tmp_path / "doc" / "tasks.md").write_text("- [ ] 甲\n- [x] 乙\n- [ ] 丙\n", encoding="utf-8")
    text = progress_doc(catalog, tmp_path)
    assert "未完成 2 项，已完成 1 项" in text
    assert "| file_library | 文件管理 | 5 | 2 | 1/2 | 1 |" in text
    assert (
        "| file_library | R-02 | 折扣比例待确认：由财务决定。 | doc/file_library/rules.md:9 |"
        in text
    )
    assert "| file_library | R-02 | 第二条 |" in text


# 按规则编号分段比较，得出新增、删除和修改的规则。
def test_rule_section_changes() -> None:
    before = sections(RULES, RULE_HEADING)
    after = sections(
        RULES.replace("已确认。", "已确认，有变化。") + "\n### R-03 第三条\n", RULE_HEADING
    )
    assert section_changes(before, after) == ["新增 R-03", "修改 R-01"]
    appended = sections(RULES + "\n## 流程\n\n图\n", RULE_HEADING)
    assert section_changes(before, appended) == []


# 文件按目录或文件名归到模块；受摘要保护的文件列为框架改动。
def test_module_and_framework_classification() -> None:
    assert belongs("server/app/api/v1/file_library.py", "file_library")
    assert belongs("doc/file_library/rules.md", "file_library")
    assert not belongs("doc/file_library_extra/rules.md", "file_library")
    found = framework_part(["server/shared/db/access.py", "doc/tasks.md"])
    assert found[-1] == "- `server/shared/db/access.py`" and len(found) == 3


# 在临时仓库中改一条规则、加一个待确认、删一个接口，报告逐项列出。
def test_impact_report(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    write(tmp_path / "doc/file_library/rules.md", RULES)
    api = {"paths": {"/a": {"get": {}}, "/b": {"get": {}}}}
    write(tmp_path / "doc/api/openapi.json", json.dumps(api))
    for args in (["init", "-q", "-b", "main"], ["add", "-A"]):
        repo.git(*args)
    repo.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "基准")
    changed = RULES.replace("已确认。", "改为待确认。")
    write(tmp_path / "doc/file_library/rules.md", changed)
    write(tmp_path / "doc/api/openapi.json", json.dumps({"paths": {"/a": {"get": {}}}}))
    write(tmp_path / "server/shared/db/access.py", "")
    text = report("main", ["file_library"], repo)
    assert "- `server/shared/db/access.py`" in text
    assert "| file_library | 业务文档 |" in text
    assert "修改 R-01；待确认 1 → 2 处" in text
    assert "- 删除接口：GET /b" in text


# 写入文件，按需要建立目录。
def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
