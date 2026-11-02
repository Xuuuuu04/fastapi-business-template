import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def lifecycle_path(value: str | None) -> Path | None:
    if value is None:
        return None
    path = Path(value).absolute()
    if path.exists() or path.is_symlink() or not path.parent.is_dir():
        raise ValueError("生命周期文件必须是已存在目录中的新文件")
    return path


def write_lifecycle(path: Path | None, run_id: str, folder: Path, phase: str) -> None:
    if path is None:
        return
    descriptor, filename = tempfile.mkstemp(prefix=".acceptance-lifecycle-", dir=path.parent)
    temporary = Path(filename)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump({"run_id": run_id, "folder": str(folder), "phase": phase}, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def temporary_folder(run_id: str, lifecycle: Path | None) -> Iterator[Path]:
    temporary = tempfile.TemporaryDirectory(prefix="fastapi-acceptance-")
    folder = Path(temporary.name)
    try:
        write_lifecycle(lifecycle, run_id, folder, "created")
        yield folder
    finally:
        temporary.cleanup()
        if folder.exists():
            raise RuntimeError("验收临时目录未被清除")
        write_lifecycle(lifecycle, run_id, folder, "cleanup_complete")
