"""
启动时检查一个流程的声明是否自洽，返回全部问题，不在第一处就停下。
检查内容：字段说明、输入与结果类型、读写字段是否存在、每个字段只有一个写入者、
读取的字段在之前是否已经有值、步骤参数与声明是否一致、写入事务开始后是否还调用大模型。
"""

from typing import Any

from shared.data.fields import FieldNote, check_notes, notes_of
from shared.data.models import Data, WorkData
from shared.flow.flow import Flow
from shared.flow.step import PARAMS, Condition, Step
from shared.model_calls.prompt import Prompt
from shared.modules.contract import Contract

MAX_STEPS = 12
ONE_KIND = ("store", "call", "model")


# 检查一个流程与它实现的操作约定，返回问题清单。
def check_flow(
    flow: Flow, contract: Contract[Any, Any], has_store: bool, prompts: tuple[Prompt, ...]
) -> list[str]:
    place = f"流程「{flow.title}」"
    if not (isinstance(flow.work, type) and issubclass(flow.work, WorkData)):
        return [f"{place} 的 work 必须是 WorkData 的子类"]
    if not (issubclass(contract.input, Data) and issubclass(contract.output, Data)):
        return [f"操作 {contract.name} 的输入和输出必须是 Data 的子类"]
    notes = notes_of(flow.work)
    problems = check_notes(flow.work, place)
    problems += check_shape(flow, contract, place)
    for item in flow.steps:
        problems += check_step(item, notes, has_store, prompts)
    problems += check_writers(flow, contract, notes)
    problems += check_sources(flow, contract, notes)
    problems += check_model_order(flow)
    return problems


# 检查输入字段、结果字段和步骤数量。
def check_shape(flow: Flow, contract: Contract[Any, Any], place: str) -> list[str]:
    problems = []
    fields = flow.work.model_fields
    for name, info in contract.input.model_fields.items():
        if name not in fields:
            problems.append(f"{place} 缺少输入字段 {name}：操作输入的字段必须在流程数据中同名出现")
        elif fields[name].annotation != info.annotation:
            problems.append(f"{place} 的字段 {name} 类型与操作输入不一致")
    result = fields.get(flow.result)
    if result is None:
        problems.append(f"{place} 的结果字段 {flow.result} 不在流程数据中")
    elif result.annotation is not contract.output:
        problems.append(f"{place} 的结果字段 {flow.result} 类型必须是 {contract.output.__name__}")
    if not flow.steps:
        problems.append(f"{place} 没有任何步骤")
    if len(flow.steps) > MAX_STEPS:
        problems.append(
            f"{place} 有 {len(flow.steps)} 个步骤，超过 {MAX_STEPS} 个；"
            "请把一部分拆成本模块的内部操作"
        )
    names = [item.name for item in flow.steps]
    for name in sorted({name for name in names if names.count(name) > 1}):
        problems.append(f"{place} 中步骤 {name} 出现了多次")
    return problems


# 检查单个步骤：读写字段存在、参数与声明一致。
def check_step(
    item: Step, notes: dict[str, FieldNote], has_store: bool, prompts: tuple[Prompt, ...]
) -> list[str]:
    place = f"步骤「{item.title}」（{item.source}）"
    problems = [
        f"{place} 读取的字段 {name} 不在流程数据中" for name in item.reads if name not in notes
    ]
    problems += [
        f"{place} 写入的字段 {name} 不在流程数据中" for name in item.writes if name not in notes
    ]
    if item.when is not None:
        problems += check_condition(item.when, notes)
    problems += check_params(item, place, has_store)
    for used in item.prompts:
        if used not in prompts:
            problems.append(f"{place} 使用的提示词「{used.title}」没有在模块声明的 prompts 中登记")
    return problems


# 检查条件读取的字段是否存在。
def check_condition(when: Condition, notes: dict[str, FieldNote]) -> list[str]:
    return [
        f"条件「{when.title}」读取的字段 {name} 不在流程数据中"
        for name in when.reads
        if name not in notes
    ]


# 检查步骤参数名与 uses、prompts、later、saves 声明是否对应。
def check_params(item: Step, place: str, has_store: bool) -> list[str]:
    params = set(item.params)
    problems = []
    if item.params[:1] != ("data",):
        problems.append(f"{place} 的第一个参数必须叫 data")
    unknown = params - set(PARAMS)
    if unknown:
        problems.append(
            f"{place} 有不认识的参数 {sorted(unknown)}，可用的参数：{', '.join(PARAMS)}"
        )
    if len(params & set(ONE_KIND)) > 1:
        problems.append(
            f"{place} 同时使用了 {sorted(params & set(ONE_KIND))}；一个步骤只做一类事，请拆开"
        )
    pairs = [
        ("call", item.uses, "uses"),
        ("model", item.prompts, "prompts"),
        ("later", item.later, "later"),
    ]
    for param, declared, option in pairs:
        if bool(declared) != (param in params):
            problems.append(f"{place} 的参数 {param} 与声明 {option}= 必须同时出现")
    if "store" in params and not has_store:
        problems.append(f"{place} 使用了 store，但所在模块没有在 module.py 中声明 store")
    if item.saves and not params & {"store", "later"}:
        problems.append(f"{place} 声明了 saves=True，但没有 store 或 later 参数")
    if "later" in params and not item.saves:
        problems.append(f"{place} 登记任务会写数据库，需要声明 saves=True")
    if item.heavy and item.is_async:
        problems.append(f"{place} 的 heavy=True 只用于普通函数（def），async 步骤不需要")
    return problems


# 检查每个字段最多只有一个写入者，且不覆盖输入字段。
def check_writers(
    flow: Flow, contract: Contract[Any, Any], notes: dict[str, FieldNote]
) -> list[str]:
    owners: dict[str, list[str]] = {}
    for item in flow.steps:
        for name in item.writes:
            owners.setdefault(name, []).append(item.title)
    problems = []
    for name, titles in owners.items():
        if len(titles) > 1:
            names = "、".join(f"「{title}」" for title in titles)
            problems.append(f"字段 {name} 被{names}同时写入；每个字段只能由一个步骤写入")
        if name in contract.input.model_fields:
            problems.append(f"步骤「{titles[0]}」覆盖了输入字段 {name}；请写入新的字段")
    return problems


# 检查每个被读取的字段在读取之前一定已经有值。
def check_sources(
    flow: Flow, contract: Contract[Any, Any], notes: dict[str, FieldNote]
) -> list[str]:
    sure = set(contract.input.model_fields) | {
        name for name, note in notes.items() if note.has_default
    }
    under: dict[Condition, set[str]] = {}
    problems = []
    for item in flow.steps:
        if item.when is not None:
            problems += [
                f"条件「{item.when.title}」读取的字段 {name}，"
                f"在步骤「{item.title}」之前还没有确定的值"
                for name in item.when.reads
                if name in notes and name not in sure
            ]
        allowed = sure | under.get(item.when, set()) if item.when is not None else sure
        problems += [
            f"步骤「{item.title}」读取的字段 {name} 在它之前没有确定的值："
            "它不是输入、没有默认值，也没有被前面不带条件的步骤写入"
            for name in item.reads
            if name in notes and name not in allowed
        ]
        target = sure if item.when is None else under.setdefault(item.when, set())
        target.update(item.writes)
    if flow.result in notes and flow.result not in sure:
        problems.append(f"流程「{flow.title}」结束时结果字段 {flow.result} 可能没有值")
    return problems


# 检查写入事务开始后是否还有大模型步骤。
def check_model_order(flow: Flow) -> list[str]:
    saving = None
    problems = []
    for item in flow.steps:
        if item.saves and saving is None:
            saving = item
        elif saving is not None and "model" in item.params:
            problems.append(
                f"步骤「{item.title}」在写入事务开始（「{saving.title}」）之后调用大模型，"
                "事务会在等待模型时一直占用数据库连接；请把大模型步骤移到第一个保存步骤之前"
            )
    return problems
