import pytest
from fastapi_project.development.integration_json import identity_merge, merge_plans


def test_identity_merge_preserves_changes_and_refuses_competing_edits() -> None:
    before = [{"id": "sample.R-01", "text": "old"}]
    local = [{"id": "sample.R-01", "text": "local"}]
    incoming = [*before, {"id": "other.R-01", "text": "new"}]
    merged = identity_merge(before, local, incoming, "id")
    assert {item["id"]: item["text"] for item in merged} == {
        "sample.R-01": "local",
        "other.R-01": "new",
    }
    with pytest.raises(ValueError, match="语义冲突"):
        identity_merge(before, local, [{"id": "sample.R-01", "text": "different"}], "id")
    with pytest.raises(ValueError, match="语义冲突"):
        identity_merge(before, [], local, "id")


def plan(operations: list[str]) -> dict:
    return {
        "schema_version": 2,
        "name": "合成计划",
        "lines": [
            {
                "name": "合成业务线",
                "packages": [
                    {
                        "module": "sample_package",
                        "title": "合成职责",
                        "kind": "capability",
                        "operations": operations,
                    }
                ],
            }
        ],
    }


def test_plan_merge_keeps_planned_operations_and_detects_purpose_conflict() -> None:
    original, local, incoming = plan(["start"]), plan(["start", "left"]), plan(["start", "right"])
    merged = merge_plans([original, local, incoming])
    assert merged["lines"][0]["packages"][0]["operations"] == ["left", "right", "start"]
    local["lines"][0]["packages"][0]["title"] = "左侧目的"
    incoming["lines"][0]["packages"][0]["title"] = "右侧目的"
    with pytest.raises(ValueError, match="语义冲突"):
        merge_plans([original, local, incoming])


def test_empty_lines_and_delete_against_new_package() -> None:
    original, local, incoming = plan(["start"]), plan(["start"]), plan(["start"])
    local["lines"].append({"name": "未来业务线", "packages": []})
    assert any(
        line["name"] == "未来业务线" for line in merge_plans([original, local, incoming])["lines"]
    )
    local["lines"] = []
    incoming["lines"][0]["packages"].append(
        {"module": "future_package", "title": "未来业务", "operations": ["start"]}
    )
    with pytest.raises(ValueError, match="业务线删除"):
        merge_plans([original, local, incoming])
