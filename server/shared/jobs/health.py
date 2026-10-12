"""
worker 的正常循环信号，保存在本容器的临时目录，不放共享业务卷。
健康状态表示最近还能领取和安排任务，不表示业务任务已经成功。
"""

from pathlib import Path

from shared.timing.current import monotonic
from shared.timing.current import now as business_now


# 以有限频率保存正常循环时间，停止时移除信号。
class WorkerHealth:
    # 绑定本进程的临时信号路径，默认关闭。
    def __init__(self, filename: str) -> None:
        self.path = Path(filename) if filename else None
        self.updated = 0.0

    # 每五秒最多写一次；未配置路径时不创建本机文件。
    def touch(self) -> None:
        if self.path is None or monotonic() - self.updated < 5:
            return
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(str(business_now()), encoding="utf-8")
        temporary.replace(self.path)
        self.updated = monotonic()

    # 启动前和停止后清除旧状态。
    def clear(self) -> None:
        if self.path is not None:
            self.path.unlink(missing_ok=True)


# 缺少、损坏、过期或来自未来的时间都不算健康。
def worker_healthy(filename: str, maximum_age: float) -> bool:
    try:
        age = business_now() - float(Path(filename).read_text(encoding="utf-8"))
        return 0 <= age <= maximum_age
    except (OSError, ValueError):
        return False
