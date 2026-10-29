import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

from shared.errors.details import safe_exception_text

request_id: ContextVar[str] = ContextVar("request_id", default="")


class JsonLines(logging.Formatter):
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


class PlainText(logging.Formatter):
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


def setup_logs(*, json_lines: bool, level: str = "INFO") -> None:
    logger = logging.getLogger("server")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLines() if json_lines else PlainText())
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
