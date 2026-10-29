import json
from pathlib import Path

import pytest
from fastapi_project.development.impact import CHECK, framework_files, impact_scope, scope_markdown
from fastapi_project.impact import Repo, belongs, report, report_data

from shared.modules.catalog import Catalog
from shared.public import (
    Call,
    Data,
    Flow,
    JobPlan,
    Later,
    Module,
    WorkData,
    contract,
    meaning,
    step,
)


class Empty(Data):
    pass


class Work(WorkData):
    result: Empty = meaning("测试结果")


a = contract("alpha.run", "甲操作", input=Empty, output=Empty, access="public")
b = contract("beta.run", "乙操作", input=Empty, output=Empty, access="public")
c = contract("gamma.run", "丙操作", input=Empty, output=Empty, access="public")
job = contract("background.run", "后台入口", input=Empty, output=Empty, access="public")
u = contract("unrelated.run", "无关操作", input=Empty, output=Empty, access="public")


@step("甲调乙", writes=["result"], uses=[b])
async def use_beta(data: Work, call: Call) -> None:
    data.result = await call(b, Empty())


@step("乙调丙", writes=["result"], uses=[c])
async def use_gamma(data: Work, call: Call) -> None:
    data.result = await call(c, Empty())


@step("安排丙任务", writes=["result"], later=[c], saves=True)
async def schedule_gamma(data: Work, later: Later) -> None:
    await later(c, Empty())
    data.result = Empty()


@step("完成", writes=["result"])
def finish(data: Work) -> None:
    data.result = Empty()


@pytest.fixture
def catalog() -> Catalog:
    return Catalog(
        [
            Module(
                "alpha", "甲", "1", {a: Flow("甲", work=Work, result="result", steps=[use_beta])}
            ),
            Module(
                "beta", "乙", "1", {b: Flow("乙", work=Work, result="result", steps=[use_gamma])}
            ),
            Module(
                "gamma",
                "丙",
                "1",
                {c: Flow("丙", work=Work, result="result", steps=[finish])},
                jobs=(JobPlan(c),),
            ),
            Module(
                "background",
                "后台",
                "1",
                {job: Flow("后台", work=Work, result="result", steps=[schedule_gamma])},
            ),
            Module(
                "unrelated",
                "无关",
                "1",
                {u: Flow("无关", work=Work, result="result", steps=[finish])},
            ),
        ]
    )


@pytest.mark.parametrize("leaf", ["steps/calculate.py", "public.py", "data.py"])
def test_reverse_transitive_calls_and_background(catalog: Catalog, leaf: str) -> None:
    scope = impact_scope([f"server/service/gamma/{leaf}"], catalog, ["beta"])
    assert scope.direct == ["gamma"]
    assert scope.dependents == ["alpha", "background", "beta"]
    assert scope.affected == ["alpha", "background", "beta", "gamma"]
    assert "unrelated" not in scope.reasons
    assert "beta" in scope.registered and "beta" not in scope.enabled
    assert any("alpha 调用 beta" in reason for reason in scope.reasons["alpha"])
    assert any("后台任务：丙操作" in reason for reason in scope.reasons["background"])
    assert scope.commands == [CHECK + " " + " ".join(f"--module {name}" for name in scope.affected)]
    assert not scope.full_check
    assert "当前启用范围" in "\n".join(scope_markdown(scope))


@pytest.mark.parametrize(
    "path",
    [
        "doc/gamma/rules.md",
        "server/tests/modules/gamma/test_rules.py",
        "server/tests/integration/gamma/test_api.py",
        "server/app/api/v1/gamma.py",
    ],
)
def test_docs_tests_and_api_are_direct_changes(catalog: Catalog, path: str) -> None:
    scope = impact_scope([path], catalog)
    assert scope.direct == ["gamma"]
    assert scope.dependents == ["alpha", "background", "beta"]
    assert path in scope.reasons["gamma"][0]
    assert not scope.full_check


@pytest.mark.parametrize(
    "path",
    [
        "server/shared/flow/runner.py",
        ".agents/skills/fastapi-project/scripts/fastapi_project/impact.py",
        "server/app/setup/catalog.py",
        "server/migrations/versions/new_table.py",
        "server/app/api/v1/__init__.py",
        "server/app/api/common.py",
        "doc/api/openapi.json",
        "server/uv.lock",
    ],
)
def test_shared_changes_check_all_registered(catalog: Catalog, path: str) -> None:
    scope = impact_scope([path], catalog, ["beta", "unrelated"])
    assert scope.full_check and scope.affected == sorted(catalog.modules)
    assert scope.commands == [CHECK]
    assert any(path in reason for reason in scope.full_check_reasons)
    assert all(scope.reasons[name] for name in catalog.modules)
    assert "unrelated" not in scope.enabled


@pytest.mark.parametrize(
    "path",
    [
        "server/service/future/public.py",
        "doc/future/rules.md",
        "server/tests/modules/future/test_rules.py",
    ],
)
def test_unknown_modules_remain_visible(catalog: Catalog, path: str) -> None:
    scope = impact_scope([path], catalog)
    assert scope.direct == scope.unknown == ["future"]
    assert scope.affected == sorted([*catalog.modules, "future"])
    assert scope.full_check and scope.commands == [CHECK]
    assert any("未登记" in reason for reason in scope.reasons["future"])


def test_unrelated_paths_and_no_changes(catalog: Catalog) -> None:
    path = "server/tests/modules/unrelated/fixtures/gamma/example.py"
    scope = impact_scope([path, "README.md"], catalog)
    assert scope.affected == scope.direct == ["unrelated"] and not scope.dependents
    assert scope.unmapped == ["README.md"]
    assert belongs(path, "unrelated") and not belongs(path, "gamma")
    assert framework_files(["server/shared_extra/example.py"]) == []
    empty = impact_scope([], catalog)
    assert empty.commands == empty.affected == [] and not empty.full_check


def test_multiple_direct_changes_are_stable(catalog: Catalog) -> None:
    paths = ["doc/beta/rules.md", "doc/gamma/rules.md", "doc/gamma/rules.md"]
    scope = impact_scope(paths, catalog)
    assert scope.direct == ["beta", "gamma"]
    assert scope.dependents == ["alpha", "background"]
    assert scope == impact_scope(reversed(paths), catalog)


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    result = Repo(tmp_path)
    write(tmp_path / "server/service/gamma/public.py", "BEFORE = 1\n")
    write(tmp_path / "doc/gamma/rules.md", "### R-01 规则\n已确认。\n")
    write(tmp_path / "doc/gamma/flows.md", "## 丙（gamma.run）\n旧流程\n")
    write(tmp_path / "doc/api/openapi.json", json.dumps({"paths": {"/old": {"get": {}}}}))
    result.git("init", "-q", "-b", "main")
    result.git("add", "-A")
    result.git(
        "-c",
        "user.name=测试",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-q",
        "-m",
        "测试初始提交",
    )
    return result


def test_git_report_preserves_all_sections_and_stable_json(repo: Repo, catalog: Catalog) -> None:
    write(repo.root / "doc/gamma/rules.md", "### R-01 规则\n待确认。\n")
    write(repo.root / "doc/gamma/flows.md", "## 丙（gamma.run）\n新流程\n")
    write(repo.root / "doc/api/openapi.json", json.dumps({"paths": {}}))
    write(repo.root / "server/migrations/versions/new.py", "# 临时迁移样例\n")
    data = report_data("main", catalog, repo, ["beta"])
    assert data["schema_version"] == 1 and data["base"] == "main"
    assert data["direct"] == ["gamma"] and data["full_check"]
    assert data["enabled"] == [name for name in sorted(catalog.modules) if name != "beta"]
    assert set(data) == {
        "schema_version",
        "base",
        "fork_point",
        "files",
        "sections",
        "direct",
        "dependents",
        "affected",
        "reasons",
        "commands",
        "full_check",
        "full_check_reasons",
        "registered",
        "enabled",
        "unknown",
        "unmapped",
    }
    assert json.loads(json.dumps(data, ensure_ascii=False)) == data
    text = report("main", catalog, repo)
    assert "修改 R-01；待确认 0 → 1 处" in text and "修改 gamma.run" in text
    assert "删除接口：GET /old" in text and "new.py" in text
    assert list(data["sections"]) == [
        "框架文件",
        "涉及的模块",
        "业务规则与待确认",
        "操作流程",
        "接口",
        "数据库迁移",
        "检查范围",
    ]


def test_git_rename_and_untracked_paths(repo: Repo, catalog: Catalog) -> None:
    (repo.root / "server/service/unrelated").mkdir()
    repo.git("mv", "server/service/gamma/public.py", "server/service/unrelated/renamed.py")
    repo.git("rm", "doc/gamma/rules.md")
    write(repo.root / "server/service/future/public.py", "NEW = 1\n")
    data = report_data("main", catalog, repo)
    assert "server/service/gamma/public.py" in data["files"]
    assert "server/service/unrelated/renamed.py" in data["files"]
    assert "doc/gamma/rules.md" in data["files"]
    assert data["direct"] == ["future", "gamma", "unrelated"] and data["unknown"] == ["future"]
    assert "| future | 代码 |" in report("main", catalog, repo)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
