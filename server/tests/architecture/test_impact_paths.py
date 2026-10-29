import pytest
from fastapi_project.development.impact import CHECK, impact_scope, module_area
from fastapi_project.impact import belongs, modules_part

from shared.modules.catalog import Catalog
from tests.architecture.sample_catalog import MODULES


@pytest.mark.parametrize(
    "path",
    [
        "server/app/api/v1/README.md",
        "server/app/api/v1/stream.py",
        "server/tests/integration/system/test_console.py",
        "server/tests/recovery/test_concurrency.py",
        "server/tests/security/test_security.py",
        "server/tests/contracts/test_cache_and_files.py",
        "server/app/api/v1/future.py",
    ],
)
def test_shared_paths_do_not_invent_modules(path: str) -> None:
    catalog = Catalog(MODULES)
    scope = impact_scope([path], catalog)
    assert scope.direct == scope.unknown == []
    assert scope.affected == sorted(catalog.modules)
    assert scope.full_check and scope.commands == [CHECK]
    assert path in scope.unmapped
    assert modules_part([path], catalog.modules) == ["没有改动业务模块。"]


def test_topic_api_uses_longest_registered_prefix() -> None:
    path = "server/app/api/v1/sample_accounts_security.py"
    assert module_area(path, ["user", "sample_accounts"]) == ("sample_accounts", "接口")


def test_topic_api_belongs_to_registered_module() -> None:
    path = "server/app/api/v1/sample_accounts_security.py"
    scope = impact_scope([path], Catalog(MODULES))
    assert scope.direct == scope.affected == ["sample_accounts"]
    assert not scope.unknown and not scope.full_check
    assert belongs(path, "sample_accounts")
    assert "sample_accounts" in "\n".join(modules_part([path], ["sample_accounts"]))
