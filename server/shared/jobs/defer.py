import math

from shared.errors.kinds import BusinessError, Kind


class RetryLater(BusinessError):
    code = "retry_later"
    kind = Kind.TEMPORARY
    message = "稍后重新核对业务状态再执行"

    def __init__(self, seconds: float, *, resource: str = "", detail: str = "") -> None:
        if not math.isfinite(seconds) or not 0 < seconds <= 86400:
            raise ValueError("延后时间必须是大于 0 且不超过 86400 的有限秒数")
        self.seconds, self.resource = seconds, resource
        super().__init__(detail or self.message)
