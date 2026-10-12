"""
组装完成后绑定同一时钟，模型、外部服务、任务、流程和运行记录不各自选择业务时间。
"""

from typing import TYPE_CHECKING

from shared.errors.framework import ConfigError
from shared.timing.clock import Clock, clock_kind

if TYPE_CHECKING:
    from app.setup.build import Services


# 绑定只赋值，不访问网络和数据库；正式环境仍由RealClock提供时间。
def bind_clock(services: "Services", clock: Clock) -> None:
    if services.settings.env == "production" and clock_kind(clock) == "simulated":
        raise ConfigError(["生产组装不能使用模拟时钟"])
    services.runtime.clock = clock
    services.queue.clock = clock
    services.remotes.clock = clock
    if services.models is not None:
        services.models.clock = clock
    if services.runtime.effects is not None:
        services.runtime.effects.clock = clock
