from typing import TYPE_CHECKING

from shared.errors.framework import ConfigError
from shared.timing.clock import Clock, clock_kind

if TYPE_CHECKING:
    from app.setup.build import Services


def bind_clock(services: "Services", clock: Clock) -> None:
    if services.settings.env == "production" and clock_kind(clock) == "simulated":
        raise ConfigError(["生产环境不能使用模拟时钟"])
    services.runtime.clock = clock
    services.queue.clock = clock
    services.remotes.clock = clock
    if services.models is not None:
        services.models.clock = clock
    if services.runtime.effects is not None:
        services.runtime.effects.clock = clock
