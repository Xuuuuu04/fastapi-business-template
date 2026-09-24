"""
两步验证码的计算规则（R-09）：与 RFC 6238 的测试向量一致；允许前后各差一个周期；
已用过的周期及更早的验证码不再接受。
"""

import base64

from service.user_access.store.totp import PERIOD, code_at, matched_step

SECRET = base64.b32encode(b"12345678901234567890").decode()


# R-09：RFC 6238 附录 B 的 SHA-1 测试向量（取后 6 位）。
def test_rfc_vectors() -> None:
    assert code_at(SECRET, 59 // PERIOD) == "287082"
    assert code_at(SECRET, 1111111109 // PERIOD) == "081804"
    assert code_at(SECRET, 1234567890 // PERIOD) == "005924"


# R-09：前后各差一个周期可以通过，差两个周期不行；用过的周期及更早的都拒绝。
def test_window_and_replay() -> None:
    now = 1_000_000.0
    step = int(now // PERIOD)
    assert matched_step(SECRET, code_at(SECRET, step - 1), now, None) == step - 1
    assert matched_step(SECRET, code_at(SECRET, step + 1), now, None) == step + 1
    assert matched_step(SECRET, code_at(SECRET, step + 2), now, None) is None
    assert matched_step(SECRET, code_at(SECRET, step), now, step) is None
    assert matched_step(SECRET, code_at(SECRET, step + 1), now, step) == step + 1
