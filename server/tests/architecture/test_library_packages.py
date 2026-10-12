"""
工具包生成、纯计算、循环、导出一致与传递调用者版本使用实际文件验证。
"""

import json
from pathlib import Path

import pytest
from fastapi_module.new_library import library_files
from fastapi_project.development.history import fingerprints
from fastapi_project.development.impact import impact_scope

from shared.errors.framework import DeclarationError
from shared.modules.catalog import Catalog
from shared.modules.libraries import library_specs
from shared.modules.validation.library_rules import check_libraries
from shared.public import Flow, Module, Nothing, WorkData, contract, meaning, step


# 文件内容来自正式生成器，测试不在真实模板里登记演示工具。
def generate(root: Path, name: str = "text_formats") -> None:
    for path, content in library_files(name, "文本格式", root).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


# 工具可以生成、读取，文件或时钟访问会指向真实源码位置。
def test_library_generation_and_purity(tmp_path: Path) -> None:
    root = tmp_path / "server"
    generate(root)
    [spec] = library_specs(root)
    assert spec.name == "text_formats" and check_libraries(root) == []
    source = root / "library/text_formats/calc/texts.py"
    source.write_text("import time\n\ndef now() -> float:\n    return time.time()\n")
    assert any(problem.rule == "calc_purity" for problem in check_libraries(root))


# 工具改动让实际使用它的模块失效，无关模块仍可沿用原结果。
def test_library_dependency_expires_only_consumers(tmp_path: Path) -> None:
    root = tmp_path / "server"
    generate(root)
    user = root / "service/text_reads/calc/texts.py"
    user.parent.mkdir(parents=True)
    user.write_text("from library.text_formats.public import normalize_text\n")
    other = root / "service/other_reads/calc/texts.py"
    other.parent.mkdir(parents=True)
    other.write_text("VALUE = 1\n")
    before = fingerprints(tmp_path, ["text_reads", "other_reads"])
    source = root / "library/text_formats/calc/texts.py"
    source.write_text(source.read_text() + "\nVALUE = 2\n")
    after = fingerprints(tmp_path, ["text_reads", "other_reads"])
    assert before["text_reads"] != after["text_reads"]
    assert before["other_reads"] == after["other_reads"]


# 两个工具互相导入不能靠声明文件的顺序掩盖循环。
def test_library_cycle_is_visible(tmp_path: Path) -> None:
    root = tmp_path / "server"
    generate(root, "text_first")
    generate(root, "text_second")
    for name, other in [("text_first", "text_second"), ("text_second", "text_first")]:
        source = root / "library" / name / "public.py"
        source.write_text(f"from library.{other}.public import normalize_text\n")
    assert any("循环" in issue.message for issue in check_libraries(root))


# 声明的导出与公开入口双向一致，任何一边多出的名称都会被指出。
def test_exports_must_match_public_all(tmp_path: Path) -> None:
    root = tmp_path / "server"
    generate(root)
    marker = root / "library/text_formats/module.json"
    original = marker.read_text()
    content = json.loads(original)
    content["exports"] = ["normalize_text", "missing_tool"]
    marker.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n")
    declared = [problem for problem in check_libraries(root) if problem.rule == "library_exports"]
    assert any("声明未公开" in problem.message for problem in declared)

    marker.write_text(original)
    public = root / "library/text_formats/public.py"
    public.write_text(
        public.read_text().replace(
            '__all__ = ["normalize_text"]', '__all__ = ["normalize_text", "extra_tool"]'
        )
    )
    exposed = [problem for problem in check_libraries(root) if problem.rule == "library_exports"]
    assert any("公开未声明" in problem.message for problem in exposed)


# __all__与声明一致仍不能导出不存在的名称，数据类的大写名称则有效。
def test_exports_require_real_bindings(tmp_path: Path) -> None:
    root = tmp_path / "server"
    generate(root)
    marker = root / "library/text_formats/module.json"
    raw = json.loads(marker.read_text())
    raw["exports"] = ["TextValue"]
    marker.write_text(json.dumps(raw))
    public = root / "library/text_formats/public.py"
    public.write_text('__all__ = ["TextValue"]\n')
    assert any("未定义" in problem.message for problem in check_libraries(root))
    public.write_text('TextValue = str\n__all__ = ["TextValue"]\n')
    assert check_libraries(root) == []


# 错误字段与重复导出返回清晰声明错误，不泄漏解释器类型异常。
@pytest.mark.parametrize("exports", [None, "tool", [1], ["class"], ["tool", "tool"]])
def test_malformed_library_exports(tmp_path: Path, exports) -> None:
    root = tmp_path / "server"
    generate(root)
    marker = root / "library/text_formats/module.json"
    raw = json.loads(marker.read_text())
    raw["exports"] = exports
    marker.write_text(json.dumps(raw))
    with pytest.raises(DeclarationError, match="有效且不重复"):
        library_specs(root)


# 无数据库的结果模型与步骤，供影响分析的登记模块使用。
class Work(WorkData):
    result: Nothing = meaning("空结果")


# 完成一次不触碰外部的空结果。
@step("返回空结果", writes=["result"])
def produce(data: Work) -> None:
    data.result = Nothing()


# 工具改动沿真实导入图投射到登记模块，间接工具同样计入，无人使用时保持未知。
def test_tool_change_reaches_real_importers(tmp_path: Path) -> None:
    root = tmp_path / "server"
    generate(root, "text_first")
    generate(root, "text_second")
    relay = root / "library/text_second/public.py"
    relay.write_text("from library.text_first.public import normalize_text\n\n__all__ = []\n")
    user = root / "service/text_reads/calc/texts.py"
    user.parent.mkdir(parents=True)
    user.write_text("from library.text_second.public import normalize_text\n")
    read = contract(
        "text_reads.read",
        "读取",
        input=Nothing,
        output=Nothing,
        access="text_reads.read",
        effect="query",
    )
    catalog = Catalog(
        [
            Module(
                "text_reads",
                "读取",
                "1",
                {read: Flow("读取", work=Work, result="result", steps=[produce])},
                kind="capability",
            )
        ]
    )

    direct = impact_scope(["server/library/text_first/calc/texts.py"], catalog, root=root)
    assert direct.direct == ["text_reads"]
    assert any("工具text_first改动" in reason for reason in direct.reasons["text_reads"])

    generate(root, "unused_tools")
    unused = impact_scope(["server/library/unused_tools/calc/texts.py"], catalog, root=root)
    assert unused.direct == [] and "server/library/unused_tools/calc/texts.py" in unused.unmapped
