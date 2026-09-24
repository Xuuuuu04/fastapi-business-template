"""
密码使用随机盐和 scrypt 摘要保存；比较采用固定时间比较。
"""

import hashlib
import secrets
from hmac import compare_digest


# 生成带随机盐的密码摘要，原文不写入数据库。
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}:{digest.hex()}"


# 账号不存在时也计算一次 scrypt，使响应时间不暴露账号是否存在。
DUMMY_HASH = hash_password("unused-password")


# 校验原文与保存的摘要是否一致。
def verify_password(password: str, saved: str) -> bool:
    salt_hex, digest_hex = saved.split(":", 1)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
    return compare_digest(digest, bytes.fromhex(digest_hex))
