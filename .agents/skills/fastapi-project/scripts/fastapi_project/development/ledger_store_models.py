"""
分包索引与写入日志的格式检查，损坏资料明确失败，不保留旧页面冒充本次成功。
"""

import json
from typing import Literal

from fastapi_project.development.ledger_models import LedgerRule, RuleEvent, RuleLedger, RuleSource
from pydantic import BaseModel, ConfigDict, Field


# 索引只管理脱敏来源和固定包名，正文属于每个包的规则文件。
class LedgerIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[2]
    generation: str = Field(pattern=r"^[a-f0-9]{32}$")
    packages: list[str]
    sources: list[RuleSource]


# 日志包含完整前后快照，文件原件是UTF8规则JSON，不能注入未知结构。
class LedgerWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    before: RuleLedger
    after: RuleLedger
    before_files: dict[str, str | None]
    after_files: dict[str, str | None]


# 包文件只保存自己的规则与事件，其他类型不能作为可读取的规则正文。
class PackageRules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    rules: list[LedgerRule]
    events: list[RuleEvent]


# 两种已知索引都先做类型检查，错误包清单不以TypeError逃过错误页面替换。
def parse_index(content: bytes) -> dict:
    raw = json.loads(content)
    if not isinstance(raw, dict):
        raise ValueError("规则索引必须为对象")
    model = (
        LedgerIndex.model_validate(raw)
        if raw.get("schema_version") == 2
        else RuleLedger.model_validate(raw)
    )
    return model.model_dump(mode="json")


# 文件集合必须含提交索引，前后快照引用也需完整，日志损坏不执行恢复。
def parse_write(content: bytes) -> dict:
    data = LedgerWrite.model_validate_json(content)
    data.before.validate_links()
    data.after.validate_links()
    if (
        "doc/rules-ledger.json" not in data.before_files
        or data.after_files.get("doc/rules-ledger.json") is None
    ):
        raise ValueError("规则写入日志缺少提交索引")
    return data.model_dump(mode="json")
