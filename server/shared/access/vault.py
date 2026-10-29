import base64
import hashlib
from collections.abc import Sequence

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from shared.errors.framework import StepRuleBroken

LOCAL_DATA_KEY = "local-development-only-data-key-change-me"


def fernet_of(key: str) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest()))


class Vault:
    def __init__(self, keys: Sequence[str]) -> None:
        if not keys:
            raise StepRuleBroken("没有配置 APP_DATA_KEYS，不能加密字段")
        self._box = MultiFernet([fernet_of(key) for key in keys])

    def encrypt(self, text: str) -> str:
        return self._box.encrypt(text.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._box.decrypt(token.encode()).decode()
        except InvalidToken:
            raise StepRuleBroken(
                "加密字段无法解密：请检查 APP_DATA_KEYS 是否包含当时使用的密钥"
            ) from None
