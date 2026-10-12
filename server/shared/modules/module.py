"""
模块声明 Module：一个业务模块对外说明自己的全部内容，写在模块的 module.py 中。
provides 把操作约定对应到实现它的流程；store 给出数据访问的实现；
tables、remotes、prompts、jobs、schedules 分别登记本模块的表、外部系统、提示词、后台任务和定时计划；
identity可声明产品会话解析操作，identity_header可显式指定兼容凭据头。
全局只在 app/setup/catalog.py 中列出启用哪些模块，不再重复登记这些内容。
"""

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


# 模块的公开操作、数据访问入口及外部依赖，统一登记到应用。
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

    # 模块的业务文档目录，位于项目根目录的 doc/ 下。
    @property
    def doc(self) -> str:
        return f"doc/{self.name}"
