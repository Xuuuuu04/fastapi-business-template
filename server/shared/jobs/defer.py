"""
明确未产生效果的冷却与延后，等待不消耗业务失败重试次数，已经产生外部效果仍转为未知。
"""

import math

from shared.errors.kinds import BusinessError, Kind


# 429等已确认可稍后执行的业务等待，不靠失败重跑掩盖未知结果。
class RetryLater(BusinessError):
    code = "retry_later"
    kind = Kind.TEMPORARY
    message = "稍后重新核对业务状态再执行"

    # 资源名必须在当前JobPlan声明，延后时间有明确上限。
    def __init__(self, seconds: float, *, resource: str = "", detail: str = "") -> None:
        if not math.isfinite(seconds) or not 0 < seconds <= 86400:
            raise ValueError("延后时间必须为一天以内的有限正秒数")
        self.seconds, self.resource = seconds, resource
        super().__init__(detail or self.message)
