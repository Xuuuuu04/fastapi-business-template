from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.data.models import Data
from shared.scenarios.observations import ObservationPosition


class ExecutionContext(Protocol):
    allowed: bool

    @property
    def observation_position(self) -> ObservationPosition: ...

    async def finish(self, connection: AsyncConnection, result: Data, run_id: str) -> None: ...
