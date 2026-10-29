import json
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from shared.records.models import RunRecord

from shared.data.models import Data
from shared.errors.framework import StepRuleBroken

MAX_CURSOR_BYTES = 16 * 1024


class Checkpoint:
    def __init__(
        self,
        number: int,
        cursor: dict[str, Any],
        before_write: Callable[[], Awaitable[None]],
        *,
        total_rows: int = 0,
        shutdown_seconds: float | None = None,
        cursor_model: type[Data] | None = None,
    ) -> None:
        self.cursor_model = cursor_model
        self.number = number
        self.total_rows = total_rows
        self.shutdown_seconds = shutdown_seconds
        self._cursor = json.dumps(cursor, ensure_ascii=False)
        self.before_write = before_write
        self.next_cursor = ""
        self.rows = 0
        self.done = False

    @property
    def cursor(self) -> dict[str, Any]:
        return dict(json.loads(self._cursor))

    def advance(self, cursor: dict[str, Any], *, rows: int) -> None:
        self.declare(cursor, rows, False)

    def finish(self, *, rows: int = 0, cursor: dict[str, Any] | None = None) -> None:
        self.declare(self.cursor if cursor is None else cursor, rows, True)

    def declare(self, cursor: dict[str, Any], rows: int, done: bool) -> None:
        if self.next_cursor:
            raise StepRuleBroken("一批只能声明一次 checkpoint.advance 或 finish")
        if not isinstance(cursor, dict) or type(rows) is not int or rows < 0:
            raise StepRuleBroken("恢复游标必须是 JSON 字典，行数必须是非负整数")
        if self.cursor_model is not None:
            cursor = self.cursor_model.model_validate(cursor).model_dump(mode="json")
        try:
            body = json.dumps(cursor, ensure_ascii=False, allow_nan=False, sort_keys=True)
        except (TypeError, ValueError) as error:
            raise StepRuleBroken("恢复游标只能包含 JSON 数据") from error
        if len(body.encode("utf-8")) > MAX_CURSOR_BYTES:
            raise StepRuleBroken("恢复游标超过16 KiB，请只保存恢复位置")
        if not done and json.loads(body) == json.loads(self._cursor):
            raise StepRuleBroken("继续下一批时必须推进恢复游标")
        self.next_cursor, self.rows, self.done = body, rows, done

    def validate(self) -> None:
        if not self.next_cursor:
            raise StepRuleBroken("分段任务每批必须声明 checkpoint.advance 或 finish")

    def record(self, run: "RunRecord", *, committed: bool = False) -> None:
        run.segment_number = self.number + 1
        run.segment_shutdown_seconds = self.shutdown_seconds
        run.segment_cursor = json.loads(self.next_cursor or self._cursor)
        run.segment_rows = self.rows if self.next_cursor else None
        run.segment_total_rows = self.total_rows + (self.rows if committed else 0)
        run.segment_committed = committed
