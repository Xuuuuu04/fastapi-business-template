"""
规则账本的来源、修订和确认数据；摘要不代替原话，文件摘要不证明修改者身份。
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# 可提交的引用只保存脱敏摘要，原文由本机忽略目录另外保管。
class RuleSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    kind: Literal["user_quote", "code", "document", "fixture"]
    summary: str = Field(min_length=1, max_length=2000)
    locator: str = Field(min_length=1, max_length=1000)
    raw_digest: str = ""


# 确认声明记录依据与修订，不从历史代码或旧文档自动推定用户确认。
class RuleConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source: str
    revision: int = Field(ge=1)
    kind: Literal["human_explicit", "fixture_only"]
    note: str = Field(min_length=1, max_length=2000)
    recorded_by: str = Field(min_length=1, max_length=200)
    recorded_at: str


# 当前规则与替代关系保留业务语义，风险由业务影响声明而不是见到数字就升级。
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


# 历史事件不能覆盖当前状态，保存当时的完整修订内容与变更理由。
class RuleEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    rule: str
    revision: int
    action: str
    reason: str = Field(min_length=1)
    recorded_at: str
    snapshot: dict[str, Any]


# 一个项目的规则索引，空模板不生成任何业务规则。
class RuleLedger(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    sources: list[RuleSource] = Field(default_factory=list)
    rules: list[LedgerRule] = Field(default_factory=list)
    events: list[RuleEvent] = Field(default_factory=list)

    # 跨记录引用与确认范围共同检查，语法正确不等于规则已经确认。
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


# 替代关系逐层检查，不用登记顺序掩盖循环。
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
