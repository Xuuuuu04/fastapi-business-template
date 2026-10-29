from typing import TYPE_CHECKING, Any

from shared.db.budget import DEFAULT_BUDGET, evaluate, policy
from shared.modules.contract import Contract
from shared.records.models import RunRecord

if TYPE_CHECKING:
    from shared.flow.runtime import Runtime


def check_query_budget(
    runtime: "Runtime", run: RunRecord, item: Contract[Any, Any], *, failed: bool = False
) -> None:
    declared = item.query_budget is not None
    mode = policy(runtime.query_policy.env)
    evaluate(run, item.query_budget or DEFAULT_BUDGET, declared, "warn" if failed else mode)
