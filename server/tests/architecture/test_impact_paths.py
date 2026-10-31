import pytest
from fastapi_check.affected.impact import impact_scope, module_area

from shared.modules.catalog import Catalog
from tests.architecture.sample_catalog import MODULES


@pytest.mark.parametrize(
    "path",
    [
        "server/app/api/v1/README.md",
        "server/app/api/system/stream.py",
        "server/tests/integration/system/test_console.py",
        "server/tests/recovery/test_concurrency.py",
        "server/tests/security/test_security.py",
        "server/tests/contracts/test_cache_and_files.py",
        "server/app/api/v1/future.py",
        "server/library/text_tools/public.py",
    ],
)
def test_shared_paths_do_not_invent_modules(path: str) -> None:
    catalog = Catalog(MODULES)
    scope = impact_scope([path], catalog)
    assert scope.direct == [] and scope.full_check
    assert path in scope.unmapped


def test_topic_api_uses_longest_registered_prefix() -> None:
    path = "server/app/api/v1/sample_accounts_security.py"
    assert module_area(path, ["user", "sample_accounts"]) == ("sample_accounts", "接口")


def test_topic_api_belongs_to_registered_module() -> None:
    path = "server/app/api/v1/sample_accounts_security.py"
    scope = impact_scope([path], Catalog(MODULES))
    assert scope.direct == ["sample_accounts"] and not scope.full_check
