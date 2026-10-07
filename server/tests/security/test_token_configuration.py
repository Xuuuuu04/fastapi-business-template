"""生产令牌配置拒绝公开开发密钥，真实密钥轮换仍然有效。"""

from pathlib import Path

import pytest

from app.setup.build import build
from shared.access.caller import Caller
from shared.access.tokens import issue_token, verify_token
from shared.config.settings import LOCAL_JWT_SECRET, check_production
from shared.errors.framework import ConfigError, NotSignedIn
from tests.testing_app import make_settings

CURRENT_SECRET = "synthetic-current-production-secret-123456789"
PREVIOUS_SECRET = "synthetic-previous-production-secret-123456789"


# 已公开开发密钥与过短密钥都必须在连接生产数据库前被拒绝。
@pytest.mark.parametrize("previous", [LOCAL_JWT_SECRET, "short-secret"])
def test_production_rejects_unsafe_previous_secret(tmp_path: Path, previous: str) -> None:
    settings = make_settings(
        tmp_path,
        env="production",
        database_url="postgresql+psycopg://example.invalid/not-used",
        code_version="test-release",
        run_records="database",
        jwt_secret=CURRENT_SECRET,
        jwt_previous_secrets=[previous],
    )
    with pytest.raises(ConfigError, match="APP_JWT_PREVIOUS_SECRETS"):
        build(settings, modules=[])


# 合法旧密钥继续通过配置检查及签名校验；清除轮换配置后旧令牌被拒绝。
def test_production_allows_independent_previous_secret(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path,
        env="production",
        database_url="postgresql+psycopg://example.invalid/not-used",
        code_version="test-release",
        run_records="database",
        jwt_secret=CURRENT_SECRET,
        jwt_previous_secrets=[PREVIOUS_SECRET],
    )
    assert not check_production(settings, needs_vault=False)
    caller = Caller("7", "user", "测试用户", frozenset({"notes.read"}), "north")
    token, _ = issue_token(caller, PREVIOUS_SECRET, settings.jwt_issuer, settings.jwt_audience, 15)
    assert (
        verify_token(
            token, [CURRENT_SECRET, PREVIOUS_SECRET], settings.jwt_issuer, settings.jwt_audience
        )
        == caller
    )
    with pytest.raises(NotSignedIn):
        verify_token(token, [CURRENT_SECRET], settings.jwt_issuer, settings.jwt_audience)
