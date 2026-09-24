"""
熔断器：外部系统或大模型连续失败达到次数后暂停调用一段时间，期间直接失败，不再每次等到超时；
暂停结束后放行一次试探，成功就恢复，失败就再暂停。状态保存在各进程内存中，多个实例各自判断。
只把“暂时不可用、结果不明”算作失败；对方明确拒绝（如参数错误）说明对方可用，不算失败。
"""

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

    # 返回还要暂停多少秒；0 表示可以调用。暂停结束后只放行一次试探。
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

    # 调用成功：清零并恢复。
    def succeeded(self) -> None:
        self.failures, self.opened_at, self.trying = 0, None, False

    # 调用失败：试探失败或连续失败达到次数时开始暂停。
    def failed(self) -> None:
        self.failures += 1
        if self.trying or self.failures >= self.threshold:
            self.opened_at, self.trying = self.clock(), False

    # 调用被取消等没有结果的情况：不算成功也不算失败，试探名额还回去。
    def released(self) -> None:
        self.trying = False

    # 当前状态，供运行状态接口展示。
    def state(self) -> str:
        if self.opened_at is None:
            return "正常"
        return "试探中" if self.trying else f"暂停（已连续失败 {self.failures} 次）"
