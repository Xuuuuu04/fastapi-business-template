from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKIP_PARTS = ("__pycache__", ".venv", "versions", "temp")


@dataclass(frozen=True)
class Problem:
    path: str
    line: int
    rule: str
    message: str
    hint: str = ""

    def text(self) -> str:
        where = f"{self.path}:{self.line}" if self.line else self.path
        tail = f" 建议：{self.hint}" if self.hint else ""
        return f"{where} [{self.rule}] {self.message}{tail}"


def relative(path: Path, root: Path = ROOT) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def files_under(root: Path, folders: Iterable[str], suffix: str) -> Iterator[Path]:
    for folder in folders:
        base = (root / folder).resolve()
        if not base.exists():
            continue
        for path in sorted(base.rglob(f"*{suffix}")):
            if not any(part in SKIP_PARTS for part in path.parts):
                yield path
