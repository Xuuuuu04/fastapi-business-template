"""
分段任务本批的恢复位置。advance/finish 只声明提交内容，执行器成功结束时与业务写入一起提交。
每次调用操作处理一批；游标只保存 JSON 数据，不保存连接、对象或外部凭据。
"""

import json
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from shared.records.models import RunRecord

from shared.data.models import Data
from shared.errors.framework import StepRuleBroken

MAX_CURSOR_BYTES = 16 * 1024


# 一批操作的已提交游标与本批提交声明，由 worker 创建并注入步骤。
class Checkpoint:
    # 从上一批已提交位置开始；外部写入前先持久化待确认标记。
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

    # 返回游标副本，修改副本不会改变恢复位置。
    @property
    def cursor(self) -> dict[str, Any]:
        return dict(json.loads(self._cursor))

    # 本批结束时提交新游标，随后用新的事务处理下一批。
    def advance(self, cursor: dict[str, Any], *, rows: int) -> None:
        self.declare(cursor, rows, False)

    # 本批结束时提交并完成整个任务；可以有最后一批数据。
    def finish(self, *, rows: int = 0, cursor: dict[str, Any] | None = None) -> None:
        self.declare(self.cursor if cursor is None else cursor, rows, True)

    # 一次调用只能声明一个提交点，非法或过大的游标拒绝保存。
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

    # 没有声明提交点就不允许保存本批业务结果。
    def validate(self) -> None:
        if not self.next_cursor:
            raise StepRuleBroken("分段任务每批必须声明 checkpoint.advance 或 finish")

    # 运行图显示恢复游标和已确认累计行数，尚未提交的本批明确标记。
    def record(self, run: "RunRecord", *, committed: bool = False) -> None:
        run.segment_number = self.number + 1
        run.segment_shutdown_seconds = self.shutdown_seconds
        run.segment_cursor = json.loads(self.next_cursor or self._cursor)
        run.segment_rows = self.rows if self.next_cursor else None
        run.segment_total_rows = self.total_rows + (self.rows if committed else 0)
        run.segment_committed = committed
