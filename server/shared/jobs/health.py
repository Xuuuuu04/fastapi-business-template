from pathlib import Path

from shared.timing.current import monotonic
from shared.timing.current import now as business_now


class WorkerHealth:
    def __init__(self, filename: str) -> None:
        self.path = Path(filename) if filename else None
        self.updated = 0.0

    def touch(self) -> None:
        if self.path is None or monotonic() - self.updated < 5:
            return
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(str(business_now()), encoding="utf-8")
        temporary.replace(self.path)
        self.updated = monotonic()

    def clear(self) -> None:
        if self.path is not None:
            self.path.unlink(missing_ok=True)


def worker_healthy(filename: str, maximum_age: float) -> bool:
    try:
        age = business_now() - float(Path(filename).read_text(encoding="utf-8"))
        return 0 <= age <= maximum_age
    except (OSError, ValueError):
        return False
