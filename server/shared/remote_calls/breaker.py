import time
from collections.abc import Callable
from dataclasses import dataclass, field

FAILURES = 5
COOLDOWN_SECONDS = 30.0


@dataclass
class Breaker:
    threshold: int = FAILURES
    cooldown: float = COOLDOWN_SECONDS
    clock: Callable[[], float] = field(default=time.monotonic)
    failures: int = 0
    opened_at: float | None = None
    trying: bool = False

    def blocked(self) -> float:
        if self.opened_at is None:
            return 0.0
        left = self.opened_at + self.cooldown - self.clock()
        if left > 0:
            return left
        if self.trying:
            return self.cooldown
        self.trying = True
        return 0.0

    def succeeded(self) -> None:
        self.failures, self.opened_at, self.trying = 0, None, False

    def failed(self) -> None:
        self.failures += 1
        if self.trying or self.failures >= self.threshold:
            self.opened_at, self.trying = self.clock(), False

    def released(self) -> None:
        self.trying = False

    def state(self) -> str:
        if self.opened_at is None:
            return "正常"
        return "试探中" if self.trying else f"暂停（已连续失败 {self.failures} 次）"
