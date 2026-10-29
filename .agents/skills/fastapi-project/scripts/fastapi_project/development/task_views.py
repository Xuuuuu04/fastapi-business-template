from pathlib import Path

from fastapi_project.development.history import read_checks
from fastapi_project.development.task_models import TaskCard, contract_digest
from fastapi_project.development.task_scope import rules_digest
from fastapi_project.development.tasks import freshness_problems

from shared.modules.catalog import Catalog


def effective_task(project: Path, catalog: Catalog, card: TaskCard, checks: dict) -> dict:
    modules = card.contract_modules or None
    reasons = []
    state = card.state
    if card.contracts != contract_digest(catalog, modules) or card.rules != rules_digest(
        project, modules
    ):
        state, reasons = "needs_update", ["相关契约或规则已变化"]
    elif card.state == "complete":
        record = checks.get(card.checks[-1]) if card.checks else None
        reasons = (
            freshness_problems(card, project, catalog, record) if record else ["检查原件未保留"]
        )
        if reasons:
            state = "incomplete"
    return {
        "id": card.id,
        "package": card.package,
        "state": state,
        "recorded_state": card.state,
        "reasons": reasons,
        "cases": card.cases,
        "checks": card.checks,
        "outside": card.outside,
        "branch": card.branch,
        "created_at": card.created_at,
        "file": f".agents/records/tasks/{card.id}.json",
    }


def task_status(project: Path, catalog: Catalog) -> list[dict]:
    paths = sorted((project / ".agents/records/tasks").glob("*.json"))
    if not paths:
        return []
    checks = {record["id"]: record for record in read_checks(project, include_cases=False)}
    return [
        effective_task(project, catalog, TaskCard.model_validate_json(path.read_bytes()), checks)
        for path in paths
    ]
