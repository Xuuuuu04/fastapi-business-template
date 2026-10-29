from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RuleSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    kind: Literal["user_quote", "code", "document", "fixture"]
    summary: str = Field(min_length=1, max_length=2000)
    locator: str = Field(min_length=1, max_length=1000)
    raw_digest: str = ""


class RuleConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source: str
    revision: int = Field(ge=1)
    kind: Literal["human_explicit", "fixture_only"]
    note: str = Field(min_length=1, max_length=2000)
    recorded_by: str = Field(min_length=1, max_length=200)
    recorded_at: str


class LedgerRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*\.R-\d+$")
    text: str = Field(min_length=1, max_length=4000)
    state: Literal["inferred", "adopted", "confirmed", "retired"] = "inferred"
    risk: Literal["low", "medium", "high"] = "medium"
    revision: int = Field(default=1, ge=1)
    sources: list[str] = Field(min_length=1)
    replaces: list[str] = Field(default_factory=list)
    confirmations: list[RuleConfirmation] = Field(default_factory=list)
    case_digests: dict[str, str] = Field(default_factory=dict)


class RuleEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    rule: str
    revision: int
    action: str
    reason: str = Field(min_length=1)
    recorded_at: str
    snapshot: dict[str, Any]


class RuleLedger(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    sources: list[RuleSource] = Field(default_factory=list)
    rules: list[LedgerRule] = Field(default_factory=list)
    events: list[RuleEvent] = Field(default_factory=list)

    def validate_links(self) -> None:
        sources = {source.id: source for source in self.sources}
        rules = {rule.id: rule for rule in self.rules}
        if len(sources) != len(self.sources) or len(rules) != len(self.rules):
            raise ValueError("账本的来源或规则编号重复")
        for rule in self.rules:
            if set(rule.sources) - sources.keys() or set(rule.replaces) - rules.keys():
                raise ValueError(f"规则 {rule.id} 引用了不存在的来源或替代对象")
            if rule.id in rule.replaces:
                raise ValueError("规则不能替代自己")
            for confirmation in rule.confirmations:
                if confirmation.source not in rule.sources or confirmation.revision > rule.revision:
                    raise ValueError("确认的来源或修订不属于当前规则")
            if rule.state == "confirmed" and not any(
                record.revision == rule.revision
                and record.kind == "human_explicit"
                and sources[record.source].kind == "user_quote"
                for record in rule.confirmations
            ):
                raise ValueError(f"规则 {rule.id} 缺少当前修订的明确人类确认来源")
        replacement_cycles(rules)


def replacement_cycles(rules: dict[str, LedgerRule]) -> None:
    for start in rules:
        pending, seen = list(rules[start].replaces), set()
        while pending:
            target = pending.pop()
            if target == start:
                raise ValueError("规则替代关系形成循环")
            if target not in seen:
                seen.add(target)
                pending.extend(rules[target].replaces)
