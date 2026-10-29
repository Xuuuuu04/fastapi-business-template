import json
from pathlib import Path

import pytest

from shared.modules.layout import check_layout, descriptor


def package(root: Path, kind: str | None, *, store: bool, extra: tuple[str, ...] = ()) -> None:
    folder = root / "service" / "order_desk"
    for name in ("data.py", "public.py", "flow.py", "module.py", *extra):
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text("", encoding="utf-8")
    (folder / "steps").mkdir()
    if store:
        (folder / "store").mkdir()
        for name in ("contract.py", "sql.py", "tables.py"):
            (folder / "store" / name).write_text("", encoding="utf-8")
    marker = descriptor("order_desk", kind=kind or "")
    (folder / "module.json").write_text(json.dumps(marker), encoding="utf-8")


@pytest.mark.parametrize(
    "kind,store,expected",
    [
        ("capability", True, []),
        ("workflow", False, []),
        ("workflow", True, ["service/order_desk/store：流程包不拥有数据，数据存取放到能力包"]),
        (None, True, ["service/order_desk/module.json：kind 必须写"]),
    ],
)
def test_layout_follows_package_kind(
    tmp_path: Path, kind: str | None, store: bool, expected: list[str]
) -> None:
    package(tmp_path, kind, store=store)
    problems = check_layout(tmp_path, ["order_desk"])
    assert len(problems) == len(expected)
    assert all(problem.startswith(text) for problem, text in zip(problems, expected, strict=True))


def test_capability_needs_store(tmp_path: Path) -> None:
    package(tmp_path, "capability", store=False)
    assert "service/order_desk/store/sql.py：缺少标准文件" in check_layout(tmp_path, ["order_desk"])


def test_flow_can_be_split_by_topic(tmp_path: Path) -> None:
    package(tmp_path, "workflow", store=False, extra=("flow_refunds.py", "data_refunds.py"))
    assert check_layout(tmp_path, ["order_desk"]) == []
