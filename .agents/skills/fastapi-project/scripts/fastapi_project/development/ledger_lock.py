"""
规则资料的本机跨进程写入锁，JSON仍是证据本体，锁文件不保存业务事实。
"""

import sqlite3
from collections.abc import Callable
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from typing import Concatenate

ACTIVE: ContextVar[Path | None] = ContextVar("rule_ledger_project", default=None)


# 完整读改写在一把本机锁内完成，避免并发命令各自覆盖另一个人的来源或修订。
def serialized[**Params, Result](
    func: Callable[Concatenate[Path, Params], Result],
) -> Callable[Concatenate[Path, Params], Result]:
    # 同一项目嵌套保存复用外层锁，异常时始终释放锁和上下文。
    @wraps(func)
    def wrapped(project: Path, /, *args: Params.args, **kwargs: Params.kwargs) -> Result:
        project = project.resolve()
        if ACTIVE.get() == project:
            return func(project, *args, **kwargs)
        path = project / ".agents/records/rules-write-lock.sqlite3"
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=30)
        token = ACTIVE.set(project)
        try:
            connection.execute("BEGIN IMMEDIATE")
            result = func(project, *args, **kwargs)
            connection.commit()
            return result
        finally:
            connection.close()
            ACTIVE.reset(token)

    return wrapped
