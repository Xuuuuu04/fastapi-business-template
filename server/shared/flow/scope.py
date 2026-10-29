from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.access.caller import Caller
from shared.db.database import Database
from shared.records.models import RemoteCallRecord
from shared.scenarios.observations import ObservationPosition

if TYPE_CHECKING:
    from shared.flow.runtime import Runtime
    from shared.jobs.checkpoint import Checkpoint


@dataclass
class Transaction:
    connection: AsyncConnection | None = None
    started_by: str = ""

    async def writer(self, database: Database, place: str) -> AsyncConnection:
        if self.connection is None:
            self.connection = await database.open_write()
            self.started_by = place
        return self.connection

    async def rollback(self) -> str:
        if self.connection is None:
            return "none"
        try:
            await self.connection.rollback()
        except Exception:
            return "unknown"
        return "rolled_back"

    async def close(self) -> None:
        if self.connection is not None:
            connection, self.connection = self.connection, None
            await connection.close()


@dataclass
class Scope:
    runtime: "Runtime"
    caller: Caller
    request_id: str
    job_id: str
    deadline: float
    depth: int = 0
    root_id: str = ""
    tx: Transaction = field(default_factory=Transaction)
    emitter: Callable[[str], Awaitable[None]] | None = None
    remote_writes: list[RemoteCallRecord] = field(default_factory=list)
    checkpoint: "Checkpoint | None" = None
    record_success: bool = True
    observation_position: ObservationPosition | None = None
