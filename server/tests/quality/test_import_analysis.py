"""
导入检查按实际源码复用解析结果；内容、路径与错误变化不能被缓存掩盖。
"""

from pathlib import Path

import pytest

from tools.quality.imports import analyzed, check_dynamic, check_service_file, imported


# 同一内容只解析一次；两处路径的诊断位置仍各自正确。
def test_same_content_reuses_parse_but_keeps_paths(tmp_path: Path) -> None:
    analyzed.cache_clear()
    source = "import shared.flow.runtime\n__import__('os')\n"
    paths = [tmp_path / "service/a/steps/x.py", tmp_path / "service/b/steps/y.py"]
    for path in paths:
        path.parent.mkdir(parents=True)
        path.write_text(source, encoding="utf-8")
        assert list(imported(path)) == [("shared.flow.runtime", 1)]
        assert check_service_file(path, tmp_path)[0].path == path.relative_to(tmp_path).as_posix()
        assert check_dynamic(path, tmp_path)[0].line == 2
    assert analyzed.cache_info().misses == 1


# 内容变化当次就被发现；错误源码仍抛出语法异常，不沿用旧成功结果。
def test_changed_content_and_invalid_syntax_are_visible(tmp_path: Path) -> None:
    analyzed.cache_clear()
    path = tmp_path / "source.py"
    path.write_text("from shared.public import Data\n", encoding="utf-8")
    assert list(imported(path)) == [("shared.public", 1)]
    path.write_text("from .internal import Data\nimportlib.import_module('os')\n", encoding="utf-8")
    assert list(imported(path)) == [(".internal", 1)]
    assert {problem.rule for problem in check_dynamic(path, tmp_path)} == {
        "import_relative",
        "import_dynamic",
    }
    path.write_text("import (\n", encoding="utf-8")
    with pytest.raises(SyntaxError):
        list(imported(path))
