"""
提供本地模板的写入密钥检查。
这不是账号系统，不包含用户、角色或会话管理。
"""

from secrets import compare_digest

from pydantic import SecretStr


# 使用固定时间比较检查写入密钥。
def valid(key: str | None, expected: SecretStr) -> bool:
    return key is not None and compare_digest(
        key.encode("utf-8"), expected.get_secret_value().encode("utf-8")
    )
