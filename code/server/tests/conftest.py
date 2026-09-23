"""
准备隔离的测试数据库和 HTTP 客户端。
测试不使用项目的真实配置或本地业务数据。
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.setup.app import create_app
from shared.config.settings import Settings
from shared.db.migrate import migrate


# 为每个测试创建独立的数据库配置。
@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        db_path=tmp_path / "test.db",
        write_key=SecretStr("test-key"),
        docs=True,
        monitor=True,
        monitor_key=SecretStr("monitor-key"),
        trace_limit=1000,
        cors=[],
    )


# 初始化临时数据库并管理应用生命周期。
@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    migrate(settings.db_path)
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        yield client
