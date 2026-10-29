import os
from pathlib import Path

import pytest
from fastapi_check.quality.rules import PROJECT

from shared.db.schema import head_revision
from tests.architecture.test_operation_generators import COPY_FLAG, run
from tests.environment import subprocess_environment
from tests.template_project import initialize


@pytest.mark.sqlite_template
def test_access_preset_passes_module_check(tmp_path: Path) -> None:
    if os.environ.get(COPY_FLAG):
        pytest.skip("模板副本不再次复制生成器验收")
    copy = tmp_path / "product"
    initialize(PROJECT, copy, "账号包验收")
    env = subprocess_environment() | {COPY_FLAG: "1"}
    entry = ["-c", "from fastapi_dev.main import main; main()"]
    preset = ["new-module", "user_access", "--title", "账号登录", "--preset", "access"]
    run(copy, [*entry, *preset], env)
    migration = next((copy / "server/migrations/versions").glob("*_user_access_accounts.py"))
    assert f'down_revision: str | None = "{head_revision()}"' in migration.read_text()
    routes = (copy / "server/app/api/v1/user_access.py").read_text()
    assert 'prefix="/api/v1/access"' in routes and '"/login"' in routes
    run(copy, [*entry, "docs"], env)
    result = run(copy, [*entry, "check", "--module", "user_access", "--workers", "0"], env)
    assert "通过  模块测试" in result and "失败  " not in result
