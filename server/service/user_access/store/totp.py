"""
基于时间的一次性验证码（TOTP，RFC 6238）：30 秒一个周期，6 位数字，HMAC-SHA1，
与常见的身份验证器应用兼容。只做计算，不读写数据库。
"""

import base64
import hashlib
import hmac
import secrets
import struct
from urllib.parse import quote

PERIOD = 30
DIGITS = 6
WINDOW = 1  # R-09：允许前后各差一个周期


# 生成 160 位随机密钥，写成身份验证器应用使用的 Base32 文字。
def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode()


# 计算某个周期的验证码。
def code_at(secret: str, step: int) -> str:
    key = base64.b32decode(secret)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10**DIGITS).zfill(DIGITS)


# 核对验证码，返回匹配的周期编号；不匹配或不晚于 after（已用过的周期）时返回 None。
def matched_step(secret: str, code: str, now: float, after: int | None) -> int | None:
    current = int(now // PERIOD)
    for step in range(current - WINDOW, current + WINDOW + 1):
        if (after is None or step > after) and hmac.compare_digest(code_at(secret, step), code):
            return step
    return None


# 生成身份验证器应用可扫描的地址（二维码内容）。
def setup_uri(secret: str, issuer: str, account: str) -> str:
    label = quote(f"{issuer}:{account}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&period={PERIOD}"
