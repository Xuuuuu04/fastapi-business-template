import fcntl
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from fastapi_project.development.check_assets import asset_path


@contextmanager
def evidence_lock(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise ValueError("证据目录不能使用链接")
    path = asset_path(root, "_write.lock")
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        deadline = time.monotonic() + 60
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise ValueError("证据正在写入或清理，请稍后重试") from None
                time.sleep(0.02)
        yield
    finally:
        os.close(descriptor)
