"""
检查监控读取权限。
监控使用独立密钥，不复用业务写入凭据。
"""

from typing import Annotated

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from shared.login.key import valid

header = APIKeyHeader(name="X-Monitor-Key", scheme_name="MonitorKey", auto_error=False)


# 只允许持有监控密钥的调用者查询运行记录。
def require_monitor(request: Request, key: Annotated[str | None, Security(header)]) -> None:
    expected = request.app.state.settings.monitor_key
    if expected is None or not expected.get_secret_value():
        raise HTTPException(503, "尚未配置监控读取密钥")
    if not valid(key, expected):
        raise HTTPException(401, "监控密钥缺失或无效")
