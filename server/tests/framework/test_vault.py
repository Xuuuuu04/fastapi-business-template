from pathlib import Path

import pytest
from pydantic import SecretStr

from shared.access.vault import LOCAL_DATA_KEY, Vault
from shared.config.settings import check_production
from shared.errors.framework import StepRuleBroken
from tests.testing_app import make_settings

OLD = "old-key-that-is-long-enough-000000"
NEW = "new-key-that-is-long-enough-111111"


def test_encrypt_and_rotate() -> None:
    saved = Vault([OLD]).encrypt("JBSWY3DPEHPK3PXP")
    assert saved != "JBSWY3DPEHPK3PXP"
    rotated = Vault([NEW, OLD])
    assert rotated.decrypt(saved) == "JBSWY3DPEHPK3PXP"
    assert Vault([NEW]).decrypt(rotated.encrypt("甲")) == "甲"
    with pytest.raises(StepRuleBroken):
        Vault([NEW]).decrypt(saved)


def test_production_needs_data_key(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, env="production")
    assert any("APP_DATA_KEYS" in item for item in check_production(settings))
    assert settings.data_keys[0].get_secret_value() == LOCAL_DATA_KEY
    good = settings.model_copy(update={"data_keys": [SecretStr(NEW)]})
    assert not any("APP_DATA_KEYS" in item for item in check_production(good))
