import json

from fastapi_docs.openapi import openapi_text
from fastapi_migration.compare_api import compare

COPY_FLAG = "TEMPLATE_COPY_RUN"


def test_compare_api() -> None:
    before = {
        "paths": {"/a": {"get": {"summary": "甲"}}, "/b": {"post": {"summary": "乙"}}},
        "components": {"schemas": {"A": {"type": "object"}, "B": {"type": "object"}}},
    }
    after = {
        "paths": {"/a": {"get": {"summary": "甲改"}}, "/c": {"get": {"summary": "丙"}}},
        "components": {"schemas": {"A": {"type": "string"}}},
    }
    assert compare(before, after) == [
        "删除接口：POST /b",
        "新增接口：GET /c",
        "接口声明变化：GET /a",
        "删除数据模型：B",
        "数据模型变化：A",
    ]
    assert compare(before, before) == []


def test_openapi_text() -> None:
    assert "/health/live" in json.loads(openapi_text())["paths"]
