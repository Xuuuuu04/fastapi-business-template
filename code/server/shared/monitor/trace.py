"""
记录模块调用的父子关系、状态和耗时。
记录保存在有容量限制的内存中，不保存业务正文或凭据。
"""

from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from threading import Lock
from time import perf_counter, time
from uuid import uuid4

request_id: ContextVar[str] = ContextVar("request_id", default="")
parent_id: ContextVar[str] = ContextVar("parent_id", default="")


@dataclass
class Span:
    id: str
    request_id: str
    parent_id: str
    caller: str
    module: str
    action: str
    version: str
    started_at: float
    started: float
    inputs: list[str]
    status: str = "running"
    output: str = ""
    error: str = ""
    elapsed_ms: float = 0


class Monitor:
    # 设置单进程记录容量和开关。
    def __init__(self, capacity: int = 1000, enabled: bool = True) -> None:
        if capacity < 1:
            raise ValueError("监控容量必须大于零")
        self.enabled = enabled
        self.rows: deque[Span] = deque(maxlen=capacity)
        self.lock = Lock()
        self.dropped = 0
        self.failures = 0

    # 记录一次调用的开始、结束及异常类型。
    @contextmanager
    def span(
        self, caller: str, module: str, action: str, version: str, inputs: list[str]
    ) -> Iterator[Span | None]:
        if not self.enabled:
            yield None
            return
        row = Span(
            id=uuid4().hex,
            request_id=request_id.get() or uuid4().hex,
            parent_id=parent_id.get(),
            caller=caller,
            module=module,
            action=action,
            version=version,
            started_at=time(),
            started=perf_counter(),
            inputs=inputs,
        )
        try:
            with self.lock:
                if len(self.rows) == self.rows.maxlen:
                    self.dropped += 1
                self.rows.append(row)
        except Exception:
            self.failures += 1
            yield None
            return
        token = parent_id.set(row.id)
        status, error = "ok", ""
        try:
            yield row
        except BaseException as cause:
            status, error = "error", type(cause).__name__
            raise
        finally:
            parent_id.reset(token)
            try:
                with self.lock:
                    row.status = status
                    row.error = error
                    row.elapsed_ms = (perf_counter() - row.started) * 1000
            except Exception:
                self.failures += 1

    # 返回指定请求或最近调用的独立快照。
    def snapshot(self, trace: str | None = None, limit: int = 100) -> dict:
        with self.lock:
            selected = [row for row in self.rows if trace is None or row.request_id == trace]
            rows = []
            for row in selected[-limit:]:
                data = asdict(row)
                data.pop("started")
                if row.status == "running":
                    data["elapsed_ms"] = (perf_counter() - row.started) * 1000
                rows.append(data)
            return {
                "items": rows,
                "matched": len(selected),
                "returned": len(rows),
                "capacity": self.rows.maxlen,
                "dropped": self.dropped,
                "failures": self.failures,
                "enabled": self.enabled,
                "limited": len(selected) > limit or self.dropped > 0,
                "storage": "process_memory",
            }
