"""
检查有界监控的实时状态和故障处理。
监控关闭或记录失败不应改变业务执行结果。
"""

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from shared.monitor.trace import Monitor, request_id


# 验证运行中的状态可读，完成后记录耗时。
def test_running() -> None:
    monitor = Monitor()
    started, finish = Event(), Event()

    # 在受控等待期间保留一个活动调用。
    def work() -> None:
        with monitor.span("api", "notes", "get", "1", []):
            started.set()
            assert finish.wait(3)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(work)
        try:
            assert started.wait(3)
            assert monitor.snapshot()["items"][0]["status"] == "running"
        finally:
            finish.set()
        future.result()
    row = monitor.snapshot()["items"][0]
    assert row["status"] == "ok"
    assert row["elapsed_ms"] >= 0


# 验证异常传播与容量淘汰都有明确记录。
def test_error_and_capacity() -> None:
    monitor = Monitor(1)
    with pytest.raises(ValueError), monitor.span("api", "notes", "create", "1", []):
        raise ValueError("不应记录的业务正文")
    assert monitor.snapshot()["items"][0]["error"] == "ValueError"
    with monitor.span("api", "notes", "get", "1", []):
        pass
    assert monitor.snapshot()["dropped"] == 1
    assert monitor.snapshot()["limited"]


# 验证关闭记录后业务仍正常执行。
def test_disabled() -> None:
    monitor = Monitor(enabled=False)
    with monitor.span("api", "notes", "get", "1", []) as row:
        assert row is None
    assert monitor.snapshot()["items"] == []


# 验证并发请求的上下文和父子关系彼此隔离。
def test_contexts() -> None:
    monitor = Monitor()

    # 为单个任务绑定请求编号并创建嵌套调用。
    def work(name: str) -> None:
        token = request_id.set(name)
        try:
            with monitor.span("api", "notes", "create", "1", []):
                with monitor.span("notes", "rules", "clean", "1", []):
                    pass
        finally:
            request_id.reset(token)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(work, ["first", "second", "third", "fourth"]))
    for name in ["first", "second", "third", "fourth"]:
        rows = monitor.snapshot(name)["items"]
        assert len(rows) == 2
        assert rows[1]["parent_id"] == rows[0]["id"]


class BrokenRows(deque):
    # 模拟记录缓存写入失败。
    def append(self, row) -> None:
        raise RuntimeError("缓存不可写")


# 验证缓存故障不会使业务调用失败。
def test_record_failure() -> None:
    monitor = Monitor()
    monitor.rows = BrokenRows(maxlen=10)
    with monitor.span("api", "notes", "get", "1", []) as row:
        assert row is None
    assert monitor.failures == 1
