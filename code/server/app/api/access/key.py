"""
检查写入接口的密钥。
声明直接进入 OpenAPI，读取示例接口保持公开。
"""

from typing import Annotated

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from shared.login.key import valid

header = APIKeyHeader(name="X-API-Key", scheme_name="WriteKey", auto_error=False)


# 拒绝未配置、缺少或错误的写入密钥。
def require_key(request: Request, key: Annotated[str | None, Security(header)]) -> None:
    expected = request.app.state.settings.write_key
    if expected is None or not expected.get_secret_value():
        raise HTTPException(503, "尚未配置写入密钥")
    if not valid(key, expected):
        raise HTTPException(401, "写入密钥缺失或无效")
