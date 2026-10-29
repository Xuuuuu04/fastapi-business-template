import json
from typing import Literal

from fastapi_project.development.ledger_models import LedgerRule, RuleEvent, RuleLedger, RuleSource
from pydantic import BaseModel, ConfigDict, Field


class LedgerIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[2]
    generation: str = Field(pattern=r"^[a-f0-9]{32}$")
    packages: list[str]
    sources: list[RuleSource]


class LedgerWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    before: RuleLedger
    after: RuleLedger
    before_files: dict[str, str | None]
    after_files: dict[str, str | None]


class PackageRules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    rules: list[LedgerRule]
    events: list[RuleEvent]


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
