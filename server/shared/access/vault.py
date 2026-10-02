"""
字段加密 Vault：需要加密保存的字段（例如两步验证密钥、身份证号）由存储实现用它加密后再写库。
密钥来自 APP_DATA_KEYS：第一把用于加密，其余只用于解密，换密钥时把旧密钥放在后面，
旧数据仍能读出，重新保存时改用新密钥。密钥原文不进入数据库和日志。
"""

import base64
import hashlib
from collections.abc import Sequence

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from shared.errors.framework import StepRuleBroken

LOCAL_DATA_KEY = "local-development-only-data-key-change-me"


# 把任意长度的密钥文字变成加密库需要的格式。
def fernet_of(key: str) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest()))


# 使用配置中的加密密钥保护数据库敏感字段，支持旧密钥读取。
class Vault:
    # 按顺序使用密钥：第一把加密，全部都可以解密。
    def __init__(self, keys: Sequence[str]) -> None:
        if not keys:
            raise StepRuleBroken("没有配置 APP_DATA_KEYS，不能加密字段")
        self._box = MultiFernet([fernet_of(key) for key in keys])

    # 加密一段文字，返回可以直接存进文本列的结果。
    def encrypt(self, text: str) -> str:
        return self._box.encrypt(text.encode()).decode()

    # 解密；密钥不对或内容被改动时报错，不返回空值。
    def decrypt(self, token: str) -> str:
        try:
            return self._box.decrypt(token.encode()).decode()
        except InvalidToken:
            raise StepRuleBroken(
                "加密字段无法解密：请检查 APP_DATA_KEYS 是否包含当时使用的密钥"
            ) from None
