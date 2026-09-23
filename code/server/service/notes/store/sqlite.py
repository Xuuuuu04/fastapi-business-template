"""
实现笔记的 SQLite 查询和保存。
SQL 集中在此，提交与回滚范围由业务入口决定。
"""

import sqlite3
from datetime import UTC, datetime

from service.notes.types import Note, NoteMissing, TitleUsed


class SqliteNotes:
    # 使用当前请求独有的数据库连接。
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # 返回自动提交或回滚的连接上下文。
    def transaction(self) -> sqlite3.Connection:
        return self.conn

    # 在一个读取事务中取得一致的总数和分页结果。
    def list(self, offset: int, limit: int) -> tuple[int, list[Note]]:
        with self.conn:
            self.conn.execute("BEGIN")
            total = self.conn.execute("SELECT count(*) FROM notes").fetchone()[0]
            rows = self.conn.execute(
                "SELECT * FROM notes ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()
        return total, [Note(**dict(row)) for row in rows]

    # 按编号查找笔记。
    def get(self, note_id: int) -> Note | None:
        row = self.conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        return Note(**dict(row)) if row else None

    # 保存新笔记并返回完整结果。
    def create(self, title: str, body: str) -> Note:
        now = datetime.now(UTC).isoformat()
        try:
            result = self.conn.execute(
                "INSERT INTO notes (title, body, created_at) VALUES (?, ?, ?)",
                (title, body, now),
            )
        except sqlite3.IntegrityError as error:
            self.conflict(error)
            raise
        return Note(id=int(result.lastrowid), title=title, body=body, created_at=now)

    # 更新指定记录并返回更新后的结果。
    def update(self, note_id: int, title: str, body: str) -> Note:
        try:
            result = self.conn.execute(
                "UPDATE notes SET title = ?, body = ? WHERE id = ?", (title, body, note_id)
            )
        except sqlite3.IntegrityError as error:
            self.conflict(error)
            raise
        if result.rowcount == 0:
            raise NoteMissing
        note = self.get(note_id)
        if note is None:
            raise NoteMissing
        return note

    # 删除指定记录并检查是否存在。
    def delete(self, note_id: int) -> None:
        result = self.conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        if result.rowcount == 0:
            raise NoteMissing

    # 仅将标题唯一约束错误转换为业务冲突。
    @staticmethod
    def conflict(error: sqlite3.IntegrityError) -> None:
        if error.sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_UNIQUE:
            raise TitleUsed from error
