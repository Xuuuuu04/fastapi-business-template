"""
提供开发视图和测试历史所需的安全步骤信息，不复制说明文字、业务取值或身份。
字段产出只保留形状；数据库调用只保留函数位置、表名、耗时和行数。
"""

from dataclasses import asdict
from typing import Any

from shared.records.models import RunRecord, StepRecord


# 使用固定字段清单，运行记录新增业务数据时不会自动进入开发历史。
def step_evidence(step: StepRecord) -> dict[str, Any]:
    names = (
        "simulated",
        "name",
        "title",
        "status",
        "source",
        "elapsed_ms",
        "reads",
        "writes",
        "outputs",
        "outputs_recorded",
        "condition",
        "condition_name",
        "condition_source",
        "condition_elapsed_ms",
        "condition_result",
        "database_count",
        "database_elapsed_ms",
        "database_complete",
        "error_code",
        "error_place",
        "children",
    )
    result = {name: getattr(step, name) for name in names}
    result["database"] = [asdict(call) for call in step.database]
    model_fields = (
        "prompt",
        "version",
        "model",
        "status",
        "elapsed_ms",
        "input_tokens",
        "output_tokens",
        "retries",
    )
    result["models"] = [
        {name: getattr(call, name) for name in model_fields} for call in step.models
    ]
    result["remotes"] = remote_evidence(step)
    return result


# 一次实际运行的名称、状态、时间和步骤；保留版本用于判断历史记录。
def run_evidence(run: RunRecord) -> dict[str, Any]:
    names = (
        "simulated",
        "id",
        "root_id",
        "parent_id",
        "parent_step",
        "status",
        "code_version",
        "source_version",
        "started_at",
        "elapsed_ms",
        "gaps",
        "planned",
        "query_budget",
    )
    return {
        **{name: getattr(run, name) for name in names},
        "operation": run.contract,
        "steps": [step_evidence(step) for step in run.steps],
    }


# 远程调用安全证据与步骤证据使用相同的固定字段原则。
def remote_evidence(step: StepRecord) -> list[dict[str, Any]]:
    remote_fields = (
        "remote",
        "method",
        "status",
        "elapsed_ms",
        "bytes_out",
        "bytes_in",
        "retries",
        "endpoint",
        "effect",
        "outcome",
    )
    return [{name: getattr(call, name) for name in remote_fields} for call in step.remotes]
