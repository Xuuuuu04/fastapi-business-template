from dataclasses import asdict, dataclass, field
from typing import Any

STEP_KIND_TEXT = {
    "compute": "计算",
    "read": "数据访问",
    "save": "保存",
    "call": "调用",
    "model": "大模型",
    "remote": "外部接口",
}

RUN_STATUS_TEXT = {
    "running": "执行中",
    "ok": "已完成",
    "failed": "失败",
    "refused": "被拒绝",
    "lost": "失去联系",
}

STEP_STATUS_TEXT = {
    "running": "执行中",
    "ok": "完成",
    "failed": "失败",
    "skipped": "跳过",
}

WRITES_TEXT = {
    "none": "没有写入数据库",
    "committed": "写入已提交",
    "rolled_back": "写入已全部撤销（数据库回滚）",
    "unknown": "保存结果尚不能确认",
    "in_parent": "写入随上层操作一起提交或撤销",
    "pending": "写入尚未提交",
}


@dataclass
class ModelCallRecord:
    prompt: str
    version: str
    model: str
    status: str
    elapsed_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    retries: int = 0
    error: str = ""
    prompt_text: str = ""
    reply_text: str = ""


@dataclass
class RemoteCallRecord:
    remote: str
    method: str
    path: str
    status: int
    elapsed_ms: float
    bytes_out: int = 0
    bytes_in: int = 0
    retries: int = 0
    error: str = ""
    outcome: str = "not_sent"
    endpoint: str = ""
    effect: str = ""
    fields: dict[str, str] = field(default_factory=dict)
    intent_id: str = ""
    provider_state: str = ""
    simulated: bool | None = None


@dataclass
class DatabaseCallRecord:
    method: str
    target: str
    statement: str
    tables: list[str]
    source: str
    function: str
    status: str = "running"
    elapsed_ms: float = 0.0
    rows: int | None = None
    error_code: str = ""
    bytes: int | None = None
    explain: list[dict[str, Any]] = field(default_factory=list)
    explain_status: str = ""
    storage_source: str = ""
    storage_function: str = ""


@dataclass
class StepRecord:
    id: str
    name: str
    title: str
    kind: str
    rule: str
    source: str
    reads: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    simulated: bool = False
    status: str = "running"
    condition: str = ""
    condition_source: str = ""
    condition_name: str = ""
    condition_elapsed_ms: float = 0.0
    condition_result: bool | None = None
    started_at: float = 0.0
    elapsed_ms: float = 0.0
    values: list[str] = field(default_factory=list)
    outputs: dict[str, str] = field(default_factory=dict)
    outputs_recorded: bool = False
    notes: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    models: list[ModelCallRecord] = field(default_factory=list)
    remotes: list[RemoteCallRecord] = field(default_factory=list)
    database: list[DatabaseCallRecord] = field(default_factory=list)
    calcs: list[str] | None = None
    database_count: int = 0
    database_elapsed_ms: float = 0.0
    database_complete: bool = False
    database_explain: bool = False
    query_limits: dict[str, int] = field(default_factory=dict)
    query_prior: dict[str, int] = field(default_factory=dict)
    database_rows: int = 0
    database_bytes: int = 0
    database_rows_unknown: int = 0
    database_bytes_unknown: int = 0
    database_functions: dict[str, dict[str, int]] = field(default_factory=dict)
    database_functions_complete: bool = True
    cache_hits: int = 0
    cache_misses: int = 0
    emitted: int = 0
    error_code: str = ""
    error_message: str = ""
    error_place: str = ""


@dataclass
class RunRecord:
    id: str
    root_id: str
    parent_id: str
    parent_step: str
    contract: str
    title: str
    module: str
    module_version: str
    code_version: str
    request_id: str
    job_id: str
    caller: str
    started_at: float
    simulated: bool = False
    status: str = "running"
    updated_at: float = 0.0
    ended_at: float = 0.0
    elapsed_ms: float = 0.0
    steps: list[StepRecord] = field(default_factory=list)
    planned: list[str] = field(default_factory=list)
    error_code: str = ""
    error_kind: str = ""
    error_message: str = ""
    failed_step: str = ""
    writes: str = "none"
    summary: str = ""
    gaps: list[str] = field(default_factory=list)
    source_version: str = ""
    clock_kind: str = ""
    import_report: dict[str, Any] = field(default_factory=dict)

    query_children: dict[str, Any] = field(default_factory=dict)
    query_budget: dict[str, Any] = field(default_factory=dict)
    segment_number: int = 0
    segment_rows: int | None = None
    segment_cursor: dict[str, Any] = field(default_factory=dict)
    segment_total_rows: int = 0
    segment_committed: bool = False
    segment_shutdown_seconds: float | None = None
    segment_warning: str = ""

    aliases: list[str] | None = None
    module_aliases: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_from_dict(data: dict[str, Any]) -> RunRecord:
    steps = []
    for raw in data.get("steps", []):
        models = [ModelCallRecord(**item) for item in raw.get("models", [])]
        remotes = [RemoteCallRecord(**item) for item in raw.get("remotes", [])]
        database = [DatabaseCallRecord(**item) for item in raw.get("database", [])]
        steps.append(
            StepRecord(**{**raw, "models": models, "remotes": remotes, "database": database})
        )
    return RunRecord(**{**data, "steps": steps})
