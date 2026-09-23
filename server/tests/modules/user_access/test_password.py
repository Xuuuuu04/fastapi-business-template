"""
确认密码摘要有随机盐且能区分正确和错误密码。
"""

from service.user_access.store.password import hash_password, verify_password


# 同一密码的摘要不同，正确密码能通过校验。
def test_password_hash() -> None:
    first, second = hash_password("correct-password"), hash_password("correct-password")
    assert first != second
    assert "correct-password" not in first
    assert verify_password("correct-password", first)
    assert not verify_password("wrong-password", first)
