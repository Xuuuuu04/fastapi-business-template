"""
设置服务日志：生产环境每条日志是一行 JSON，本地开发是易读的文本；每条都带当前请求编号。
日志不记录请求正文、密钥和业务数据原文；按运行编号查看业务过程请用排查接口。
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

from shared.errors.details import safe_exception_text

request_id: ContextVar[str] = ContextVar("request_id", default="")


# 将一条日志格式化为一行 JSON，方便日志服务读取。
class JsonLines(logging.Formatter):
    # 把一条日志整理成一行 JSON。
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id.get(),
        }
        if record.exc_info:
            error = record.exc_info[1]
            if error is not None:
                data["error"] = safe_exception_text(error)
        return json.dumps(data, ensure_ascii=False)


# 将日志格式化为本地开发可直接阅读的文本。
class PlainText(logging.Formatter):
    # 把一条日志整理成便于本地阅读的一行文本。
    def format(self, record: logging.LogRecord) -> str:
        moment = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        text = f"{moment} {record.levelname:<7} {record.name} {record.getMessage()}"
        if request_id.get():
            text += f" request_id={request_id.get()}"
        if record.exc_info:
            error = record.exc_info[1]
            if error is not None:
                text += "\n" + safe_exception_text(error)
        return text


# 为 server 开头的日志设置输出格式和级别。
def setup_logs(*, json_lines: bool, level: str = "INFO") -> None:
    logger = logging.getLogger("server")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLines() if json_lines else PlainText())
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
