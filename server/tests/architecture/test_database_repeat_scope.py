"""
仅在同轮前库成功后省去固定 SQLite 模板重复，真实数据库测试保持选择。
"""

from types import SimpleNamespace
from typing import Any

import pytest

from tests.conftest import pytest_collection_modifyitems as select_database_cases


# 三种模式区分普通执行、双库前轮成功、前轮失败。
@pytest.mark.parametrize("repeat,expected", [(None, 0), ("0", 0), ("1", 1)])
def test_only_fixed_sqlite_template_is_skipped(
    repeat: str | None, expected: int, monkeypatch: pytest.MonkeyPatch, pytestconfig: pytest.Config
) -> None:
    monkeypatch.delenv("APP_DEVELOPMENT_REPEAT_DATABASE", raising=False)
    monkeypatch.setenv("APP_TEST_DATABASE_URL", "postgresql://localhost/test")
    if repeat is not None:
        monkeypatch.setenv("APP_DEVELOPMENT_REPEAT_DATABASE", repeat)
    template_marks: list[Any] = []
    database_marks: list[Any] = []
    items = [
        SimpleNamespace(
            name="template", keywords={"sqlite_template"}, add_marker=template_marks.append
        ),
        SimpleNamespace(
            name="database", keywords={"postgres_only"}, add_marker=database_marks.append
        ),
    ]
    select_database_cases(pytestconfig, items)  # type: ignore[arg-type]
    assert len(template_marks) == expected
    assert database_marks == []
