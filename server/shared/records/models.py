"""
定义运行记录的结构：一次操作的运行、其中每个步骤、每次大模型调用。
记录只保存状态、耗时、字段摘要和说明，不保存业务数据原文。
"""

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


# 一次大模型调用的版本、耗时、用量和失败信息。
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


# 一次外部接口请求的耗时、状态、大小和重试记录。
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


# 一次业务数据库调用的位置、耗时和行数；不保存 SQL 文本、参数或查询结果。
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


# 一次步骤执行的状态、字段摘要、外部调用与失败位置。
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
    database_count: int = 0
    database_elapsed_ms: float = 0.0
    database_complete: bool = False
    cache_hits: int = 0
    cache_misses: int = 0
    emitted: int = 0
    error_code: str = ""
    error_message: str = ""
    error_place: str = ""


# 一个公开操作的完整执行记录，关联请求、任务和上下层调用。
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

    # 转成可以保存为 JSON 的字典。
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# 从保存的字典恢复运行记录。
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
