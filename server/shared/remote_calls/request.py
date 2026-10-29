from dataclasses import dataclass
from typing import Any, Literal

from shared.data.models import Data
from shared.records.models import RemoteCallRecord
from shared.remote_calls.endpoint import Endpoint


@dataclass(frozen=True)
class FilePart:
    field: str
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"


@dataclass(frozen=True)
class RemoteReply:
    status: int
    data: Any
    text: str
    content: bytes


@dataclass(frozen=True)
class RemoteRequest:
    method: str
    path: str
    endpoint: str
    effect: Literal["read", "write"]
    params: dict[str, Any] | None = None
    json: Any = None
    key: str = ""
    accepted_statuses: tuple[int, ...] = ()
    unknown_on: tuple[int, ...] = ()
    protocol: Endpoint[Any, Any] | None = None
    input: Data | None = None
    files: tuple[FilePart, ...] = ()
    form: dict[str, str] | None = None

    def record(self, remote: str) -> RemoteCallRecord:
        path = self.protocol.path if self.protocol else self.path.split("?")[0]
        record = RemoteCallRecord(remote, self.method, path, 0, 0)
        record.endpoint, record.effect = self.endpoint, self.effect
        record.bytes_out = len(str(self.json or self.form or "").encode()) + sum(
            len(part.content) for part in self.files
        )
        return record


def is_write(request: RemoteRequest) -> bool:
    return request.effect == "write"
