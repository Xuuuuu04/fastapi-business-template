from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import Table

from shared.data.models import Data
from shared.effects.spec import ProviderSpec
from shared.flow.flow import Flow
from shared.jobs.plan import JobPlan, Schedule
from shared.model_calls.prompt import Prompt
from shared.modules.contract import Contract
from shared.remote_calls.endpoint import Endpoint
from shared.remote_calls.remote import Remote

if TYPE_CHECKING:
    from shared.pipelines.plan import Pipeline

STORE_PARAMS = ("db", "legacy", "remote", "files", "cache", "caller", "vault")


@dataclass(frozen=True, eq=False)
class Module:
    name: str
    title: str
    version: str
    provides: Mapping[Contract[Any, Any], Flow]
    store: Callable[..., object] | None = None
    tables: tuple[Table, ...] = ()
    remotes: tuple[Remote, ...] = ()
    prompts: tuple[Prompt, ...] = ()
    jobs: tuple[JobPlan, ...] = ()
    schedules: tuple[Schedule, ...] = ()
    identity: Contract[Any, Any] | None = None
    identity_header: str = ""
    identity_token: Literal["jwt", "opaque"] = "jwt"
    pipelines: tuple["Pipeline", ...] = ()
    endpoints: tuple[Endpoint[Any, Any], ...] = ()

    aliases: tuple[str, ...] = ()
    owned_tables: tuple[str, ...] = ()
    external_tables: tuple[str, ...] = ()
    kind: Literal["capability", "workflow"] | None = None
    read_dependencies: tuple[str, ...] = ()
    boundary_data: tuple[type[Data], ...] = ()
    providers: tuple[ProviderSpec, ...] = ()

    @property
    def doc(self) -> str:
        return f"doc/{self.name}"
