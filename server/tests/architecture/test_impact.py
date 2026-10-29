import pytest
from fastapi_check.affected.impact import framework_files, impact_scope, module_area

from shared.modules.catalog import Catalog
from shared.public import Data, Flow, Module, WorkData, contract, meaning, step


class Empty(Data):
    pass


class Work(WorkData):
    result: Empty = meaning("测试结果")


@step("完成", writes=["result"])
def finish(data: Work) -> None:
    data.result = Empty()


def sample_module(name: str, title: str) -> Module:
    operation = contract(
        f"{name}.run", f"{title}操作", input=Empty, output=Empty, access="public", effect="command"
    )
    flow = Flow(title, work=Work, result="result", steps=[finish])
    return Module(name, title, "1", {operation: flow}, kind="capability")


@pytest.fixture
def catalog() -> Catalog:
    return Catalog([sample_module("beta", "乙"), sample_module("gamma", "丙")])


@pytest.mark.parametrize(
    "path",
    [
        "server/service/gamma/steps/calculate.py",
        "server/service/gamma/public.py",
        "server/tests/modules/gamma/test_rules.py",
        "server/tests/integration/gamma/test_api.py",
        "server/app/api/v1/gamma.py",
    ],
)
def test_module_files_are_direct_changes(catalog: Catalog, path: str) -> None:
    scope = impact_scope([path], catalog)
    assert scope.direct == ["gamma"]
    assert not scope.full_check and scope.unmapped == []


def test_doc_folders_do_not_belong_to_modules(catalog: Catalog) -> None:
    path = "doc/gamma/cases/c.json"
    assert module_area(path, ["gamma"]) is None
    scope = impact_scope([path], catalog)
    assert scope.direct == [] and scope.unmapped == [path]


def test_business_document_needs_no_check(catalog: Catalog) -> None:
    paths = [
        ".agents/skills/fastapi-business/business.md",
        ".agents/skills/fastapi-business/business/a.md",
    ]
    scope = impact_scope(paths, catalog)
    assert not scope.full_check and scope.direct == scope.unmapped == []


@pytest.mark.parametrize(
    "path",
    [
        "server/shared/flow/runner.py",
        ".agents/skills/fastapi-check/scripts/fastapi_check/affected/impact.py",
        "server/app/setup/catalog.py",
        "server/migrations/versions/new_table.py",
        "server/app/api/v1/__init__.py",
        "server/app/api/common.py",
        "doc/api/openapi.json",
        "server/uv.lock",
    ],
)
def test_shared_changes_need_full_check(catalog: Catalog, path: str) -> None:
    scope = impact_scope([path], catalog)
    assert scope.full_check
    assert any(path in reason for reason in scope.full_check_reasons)


@pytest.mark.parametrize(
    "path", ["server/service/future/public.py", "server/tests/modules/future/test_rules.py"]
)
def test_unknown_modules_need_full_check(catalog: Catalog, path: str) -> None:
    scope = impact_scope([path], catalog)
    assert scope.direct == ["future"] and scope.full_check
    assert any("模块 future 未登记" in reason for reason in scope.full_check_reasons)


def test_unrelated_paths_and_no_changes(catalog: Catalog) -> None:
    path = "server/tests/modules/beta/fixtures/gamma/example.py"
    scope = impact_scope([path, "README.md"], catalog)
    assert scope.direct == ["beta"] and scope.unmapped == ["README.md"]
    assert module_area(path, ["beta"]) == ("beta", "测试")
    assert module_area(path, ["gamma"]) != ("gamma", "测试")
    assert framework_files(["server/shared_extra/example.py"]) == []
    empty = impact_scope([], catalog)
    assert empty.direct == [] and not empty.full_check


def test_multiple_direct_changes_are_stable(catalog: Catalog) -> None:
    paths = [
        "server/service/beta/public.py",
        "server/service/gamma/public.py",
        "server/service/gamma/public.py",
    ]
    scope = impact_scope(paths, catalog)
    assert scope.direct == ["beta", "gamma"]
    assert scope == impact_scope(reversed(paths), catalog)
