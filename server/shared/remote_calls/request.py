"""
远程传输数据与兼容的效果判断。
"""

from dataclasses import dataclass
from typing import Any

from shared.data.models import Data
from shared.records.models import RemoteCallRecord
from shared.remote_calls.endpoint import Endpoint

SAFE_METHODS = ("GET", "HEAD")


# 小文件正文显式携带名称和格式，大文件通过产物流接入，不能隐式读取任意本地文件。
@dataclass(frozen=True)
class FilePart:
    field: str
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"


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
    input: Data | None = None
    files: tuple[FilePart, ...] = ()
    form: dict[str, str] | None = None

    # 只记录模板路径与数据大小，路径实参和文件正文不进入诊断摘要。
    def record(self, remote: str) -> RemoteCallRecord:
        path = self.protocol.path if self.protocol else self.path.split("?")[0]
        record = RemoteCallRecord(remote, self.method, path, 0, 0)
        record.endpoint, record.effect = self.endpoint, self.effect
        record.bytes_out = len(str(self.json or self.form or "").encode()) + sum(
            len(part.content) for part in self.files
        )
        return record


# 新声明按业务效果判断；旧请求沿用HTTP方法的原行为。
def is_write(request: RemoteRequest) -> bool:
    return (
        request.effect == "write" if request.effect else request.method.upper() not in SAFE_METHODS
    )
