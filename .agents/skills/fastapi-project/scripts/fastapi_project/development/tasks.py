"""
开工资料与收工核对使用实际声明、规则和本次检查，模拟、旧证据和跳过不能算完成。
"""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi_project.development.check_assets import atomic_bytes
from fastapi_project.development.check_storage import load_cases
from fastapi_project.development.confirmed_cases import CaseFixture, case_problems
from fastapi_project.development.evidence import system_fingerprint
from fastapi_project.development.history import fingerprints
from fastapi_project.development.ledger import read_ledger
from fastapi_project.development.task_baseline import save_baseline
from fastapi_project.development.task_models import (
    TaskCard,
    branch_name,
    contract_digest,
    save_card,
    source_snapshot,
)
from fastapi_project.development.task_scope import rules_digest, scope_modules

from shared.modules.catalog import Catalog


# 必须引用独立样例，未知编号不创建一张看似已定义好完成条件的任务卡。
def fixtures(project: Path, package: str, identities: list[str]) -> list[CaseFixture]:
    found = [
        CaseFixture.model_validate_json(path.read_bytes())
        for path in (project / "doc" / package / "cases").glob("*.json")
    ]
    selected = [case for case in found if case.id in identities]
    if len(selected) != len(identities) or len(set(identities)) != len(identities):
        raise ValueError("任务样例未定义或编号重复，请先独立填写输入、初始状态与预期")
    return selected


# 阅读资料只列有界引用，不把原话或样例里的业务原文复制进任务卡输出。
def start_task(project: Path, catalog: Catalog, package: str, identities: list[str]) -> TaskCard:
    if package not in catalog.modules:
        raise ValueError("业务包还未登记，请先声明契约与骨架")
    identities = [
        name if name.startswith(package + ".") else package + "." + name for name in identities
    ]
    selected = fixtures(project, package, identities)
    modules = scope_modules(catalog, package)
    reading = reading_paths(project, catalog, package, identities, selected)
    card = TaskCard(
        id=uuid.uuid4().hex,
        package=package,
        cases=identities,
        created_at=datetime.now(UTC).isoformat(),
        branch=branch_name(project),
        contract_modules=modules,
        contracts=contract_digest(catalog, modules),
        rules=rules_digest(project, modules),
        allowed=[
            f"server/service/{package}/steps/",
            f"server/service/{package}/calc/",
            f"server/service/{package}/store/sql.py",
            f"server/tests/modules/{package}/",
            f"server/tests/integration/{package}/",
        ],
        before=source_snapshot(project),
        reading=reading[:16],
        reading_omitted=max(0, len(reading) - 16),
    )
    save_baseline(project, card.id, card.before)
    save_card(project, card)
    return card


# 本包与相邻步骤提供有界引用，原话资料保留原件，不自动复制到卡片。
def reading_paths(
    project: Path,
    catalog: Catalog,
    package: str,
    identities: list[str],
    selected: list[CaseFixture],
) -> list[str]:
    reading = [
        f"doc/{package}/needs.md",
        f"doc/{package}/rules.md",
        f"doc/{package}/ledger.md",
        f"server/service/{package}/public.py",
        f"server/service/{package}/data.py",
    ]
    reading += [
        f"doc/{package}/cases/{path.name}"
        for path in sorted((project / "doc" / package / "cases").glob("*.json"))
        if CaseFixture.model_validate_json(path.read_bytes()).id in identities
    ]
    reading += ["server/" + test.partition("::")[0] for case in selected for test in case.tests]
    reading += [
        "server/" + part.source.partition(":")[0]
        for binding in catalog.bindings.values()
        if binding.module.name == package
        for part in binding.flow.steps
    ]
    return list(dict.fromkeys(reading))


# 当前包和所有实际调用方一起检查，避免只测孤立步骤就宣布整条链可用。
def related_modules(catalog: Catalog, package: str) -> tuple[str, ...]:
    links = catalog.links()
    selected = {package}
    while True:
        expanded = selected | {name for name, targets in links.items() if set(targets) & selected}
        if selected == expanded:
            break
        selected = expanded
    return tuple(sorted(selected))


# 变化清单包含新增和删除，不能只检查仍然存在的文件。
def changed_files(card: TaskCard, project: Path) -> list[str]:
    current = source_snapshot(project)
    return sorted(
        name
        for name in card.before.keys() | current.keys()
        if card.before.get(name) != current.get(name)
    )


# 检查来源时间、范围和代码指纹，当前样例成功不代表完整相关链已检查。
def freshness_problems(
    card: TaskCard, project: Path, catalog: Catalog, record: dict[str, Any]
) -> list[str]:
    if card.package not in record["fingerprints"] or record.get("scope", {}).get("kind") not in {
        "all",
        "module",
        "modules",
    }:
        return ["本次检查没有完整覆盖任务所在包"]
    finished = record.get("finished_at")
    if not finished or datetime.fromisoformat(finished) < datetime.fromisoformat(card.created_at):
        return ["缺少开工后的本次检查证据"]
    if not set(related_modules(catalog, card.package)) <= record["fingerprints"].keys():
        return ["本次检查没有覆盖实际调用链"]
    codes = fingerprints(project, list(record["fingerprints"]), catalog.links())
    failures = [
        f"{name}：检查未通过" + ("，请运行 uv run dev docs" if name == "生成文档" else "")
        for name, passed in record.get("checks", {}).items()
        if not passed
    ]
    failures += record.get("problems", [])
    if not record["passed"]:
        return failures or ["本次检查未通过，请查看本轮检查记录"]
    if (
        record["source_changed"]
        or codes != record["fingerprints"]
        or record.get("system_fingerprint") != system_fingerprint(project)
    ):
        return ["检查之后代码又改过了，结果不属于当前源码，请重新运行 uv run dev finish"]
    return []


# 读取新鲜本次证据；模拟轨迹、跳过和源版本变化都不能成为完成条件。
def evidence_problems(
    card: TaskCard,
    project: Path,
    catalog: Catalog,
    record: dict[str, Any],
    databases: tuple[str, ...],
) -> list[str]:
    freshness = freshness_problems(card, project, catalog, record)
    if freshness:
        return freshness
    suites = {suite["database"]: suite for suite in record["suites"]}
    problems = []
    for database in databases:
        if database not in suites:
            problems.append(f"本次没有{database}检查证据")
            continue
        if suites[database].get("exit_code") != 0:
            problems.append(f"本次{database}整轮测试未通过")
        cases = load_cases(suites[database])
        for identity in card.cases:
            actual = [case for case in cases if identity in case.get("scenario_ids", [])]
            if not actual or any(case["outcome"] != "passed" for case in actual):
                problems.append(f"{database}样例{identity}未完整通过")
            if any(
                run.get("simulated")
                and (not run.get("operation") or run["operation"].startswith(card.package + "."))
                for case in actual
                for run in case.get("runs", [])
            ):
                problems.append(f"{database}样例{identity}仍包含模拟执行")
    return problems


# 任务范围、契约和确认样例各自核对；范围外改动列入审查，不藏进检查成功里。
def finish_task(
    project: Path,
    catalog: Catalog,
    card: TaskCard,
    record: dict[str, Any],
    databases: tuple[str, ...],
) -> TaskCard:
    changes = changed_files(card, project)
    card.outside = [
        name
        for name in changes
        if not any(
            name == allowed or (allowed.endswith("/") and name.startswith(allowed))
            for allowed in card.allowed
        )
    ]
    stale = card.contracts != contract_digest(
        catalog, card.contract_modules or None
    ) or card.rules != rules_digest(project, card.contract_modules or None)
    problems = ["任务契约或规则已经变化，请更新任务卡"] if stale else []
    problems += case_problems(project, read_ledger(project), delivery=False)
    problems += evidence_problems(card, project, catalog, record, databases)
    problems += [
        f"规则与实现状态：{binding.contract.name} 仍是模拟实现（{part.source}），"
        "请替换步骤并设置 simulated=False"
        for binding in catalog.bindings.values()
        if binding.module.name == card.package
        for part in binding.flow.steps
        if part.simulated
    ]
    card.state = "needs_update" if stale else "incomplete" if problems else "complete"
    card.problems = problems
    card.checks = list(dict.fromkeys([*card.checks, record["id"]]))
    save_card(project, card)
    review = {
        "task": card.id,
        "checks": card.checks,
        "state": card.state,
        "outside": card.outside,
        "problems": problems,
        "contract_changes": stale,
        "changes": changes,
    }
    atomic_bytes(
        project / ".agents/records/reviews" / (card.id + ".json"),
        json.dumps(review, ensure_ascii=False, indent=2).encode(),
    )
    return card
