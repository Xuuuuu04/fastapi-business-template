"""
worker共用的阶段完成接口；普通阶段和扇出成员都遵守同一个事务提交回调。
"""

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.data.models import Data
from shared.scenarios.observations import ObservationPosition


# 只暴露worker需要的能力，不让worker了解成员状态机。
class ExecutionContext(Protocol):
    allowed: bool

    # 成员与尝试位置由状态机提供，不让worker推断业务字段。
    @property
    def observation_position(self) -> ObservationPosition: ...

    # 在业务事务提交前登记实际结果及下一步。
    async def finish(self, connection: AsyncConnection, result: Data, run_id: str) -> None: ...
