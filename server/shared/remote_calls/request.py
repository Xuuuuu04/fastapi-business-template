"""
远程传输数据与兼容的效果判断。
"""

from dataclasses import dataclass
from typing import Any

from shared.remote_calls.endpoint import Endpoint

SAFE_METHODS = ("GET", "HEAD")


# 外部接口返回的状态与内容，供数据访问实现转换为业务数据。
@dataclass(frozen=True)
class RemoteReply:
    status: int
    data: Any
    text: str
    content: bytes


# 发送给外部系统的请求内容，包含方法、路径和请求编号。
@dataclass(frozen=True)
class RemoteRequest:
    method: str
    path: str
    params: dict[str, Any] | None = None
    json: Any = None
    key: str = ""
    accepted_statuses: tuple[int, ...] = ()
    endpoint: str = ""
    effect: str = ""
    unknown_on: tuple[int, ...] = ()
    protocol: Endpoint[Any, Any] | None = None


# 新声明按业务效果判断；旧请求沿用HTTP方法的原行为。
def is_write(request: RemoteRequest) -> bool:
    return (
        request.effect == "write" if request.effect else request.method.upper() not in SAFE_METHODS
    )
