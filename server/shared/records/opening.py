import secrets
from typing import TYPE_CHECKING

from shared.flow.scope import Scope
from shared.modules.catalog import Binding
from shared.records.models import RunRecord, StepRecord
from shared.timing.clock import clock_kind
from shared.timing.current import now as business_now

if TYPE_CHECKING:
    from shared.flow.runtime import Runtime


def open_record(
    runtime: "Runtime",
    binding: Binding,
    scope: Scope,
    parent: RunRecord | None,
    step: StepRecord | None,
) -> RunRecord:
    run_id = secrets.token_hex(8)
    run = RunRecord(
        id=run_id,
        root_id=parent.root_id if parent else run_id,
        parent_id=parent.id if parent else "",
        parent_step=step.id if step else "",
        contract=binding.contract.name,
        title=binding.contract.title,
        aliases=list(binding.contract.aliases),
        module_aliases=list(binding.module.aliases),
        module=binding.module.name,
        module_version=binding.module.version,
        code_version=runtime.code_version,
        clock_kind=clock_kind(runtime.clock),
        request_id=scope.request_id,
        job_id=scope.job_id,
        caller=f"{scope.caller.kind}:{scope.caller.id}",
        started_at=business_now(),
        planned=[part.name for part in binding.flow.steps],
    )
    if scope.checkpoint is not None:
        scope.checkpoint.record(run)
    runtime.recorder.start(run, record_success=scope.record_success)
    return run
