import sqlite3
from collections.abc import Callable
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from typing import Concatenate

ACTIVE: ContextVar[Path | None] = ContextVar("rule_ledger_project", default=None)


def serialized[**Params, Result](
    func: Callable[Concatenate[Path, Params], Result],
) -> Callable[Concatenate[Path, Params], Result]:
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
