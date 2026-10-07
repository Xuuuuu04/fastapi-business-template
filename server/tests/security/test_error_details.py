"""意外异常日志保留实际调用位置，去除消息、源码与变量中的业务值。"""

import json
import logging
import sys

import pytest

from shared.errors.details import safe_exception_text
from shared.errors.framework import FileTooLarge
from shared.logs.setup import JsonLines, PlainText
from shared.records.models import RunRecord
from shared.records.recorder import Recorder
from shared.records.stores import MemoryRunStore


# 返回携带敏感消息及原因的异常，用于检查日志的两种实际输出格式。
def failed_request() -> None:
    try:
        raise ValueError("synthetic-sensitive-token")
    except ValueError as error:
        raise RuntimeError("synthetic-sensitive-password") from error


# JSON 与本地文本日志都只保留类型与位置，不格式化原始异常消息和源码。
@pytest.mark.parametrize("formatter", [JsonLines(), PlainText()])
def test_exception_log_omits_messages(formatter: logging.Formatter) -> None:
    try:
        failed_request()
    except RuntimeError:
        record = logging.LogRecord(
            "server", logging.ERROR, __file__, 1, "request_failed", (), sys.exc_info()
        )
    else:
        raise AssertionError("测试请求应失败")
    text = formatter.format(record)
    assert "synthetic-sensitive" not in text
    assert "RuntimeError" in text and "failed_request" in text
    assert "test_error_details.py:" in text
    if isinstance(formatter, JsonLines):
        assert "RuntimeError" in json.loads(text)["error"]


# 已定义的业务错误保留公开的中文原因。
def test_business_error_keeps_public_reason() -> None:
    error = FileTooLarge("文件超过 10 MB")
    assert safe_exception_text(error) == "FileTooLarge：文件超过 10 MB"


# 保存故障模拟数据库驱动在异常消息中带出敏感参数。
class BrokenRecordStore(MemoryRunStore):
    # 只模拟保存错误，不写入任何真实记录。
    async def save(self, runs: list[RunRecord]) -> None:
        raise OSError("database parameter=synthetic-sensitive-password")


# 记录器的故障入口不把原始异常交给日志处理器，同时保留失败计数。
@pytest.mark.anyio
async def test_recorder_failure_uses_safe_log(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("server.records")
    logger.addHandler(caplog.handler)
    try:
        recorder = Recorder(BrokenRecordStore(10))
        run = RunRecord("r", "r", "", "", "c", "t", "m", "1", "dev", "", "", "x", 0.0)
        await recorder.save([run])
        assert recorder.failures == 1
        assert "synthetic-sensitive" not in caplog.text
        assert "OSError" in caplog.text and "save" in caplog.text
        assert all(record.exc_info is None for record in caplog.records)
    finally:
        logger.removeHandler(caplog.handler)
