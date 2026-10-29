import hashlib
import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from fastapi_project.development.check_assets import atomic_bytes
from pydantic import BaseModel, ConfigDict, Field

from shared.modules.catalog import Catalog


class TaskCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    package: str
    cases: list[str] = Field(min_length=1)
    state: Literal["active", "needs_update", "incomplete", "complete"] = "active"
    created_at: str
    branch: str
    contract_modules: list[str] = Field(default_factory=list)
    contracts: str
    rules: str
    allowed: list[str]
    before: dict[str, str]
    reading: list[str]
    reading_omitted: int = 0
    checks: list[str] = Field(default_factory=list)
    outside: list[str] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)


def card_path(project: Path, identity: str) -> Path:
    if len(identity) != 32 or any(letter not in "0123456789abcdef" for letter in identity):
        raise ValueError("任务编号不合法")
    return project / ".agents/records/tasks" / (identity + ".json")


def save_card(project: Path, card: TaskCard) -> None:
    atomic_bytes(card_path(project, card.id), (card.model_dump_json(indent=2) + "\n").encode())


def read_card(project: Path, identity: str) -> TaskCard:
    return TaskCard.model_validate_json(card_path(project, identity).read_bytes())


def source_snapshot(project: Path) -> dict[str, str]:
    paths = [
        project / name
        for name in (
            "AGENTS.md",
            "project-plan.json",
            "README.md",
            "server/pyproject.toml",
            "server/uv.lock",
            "server/framework.lock",
        )
    ]
    folders = (
        "server/app",
        "server/shared",
        "server/service",
        "server/library",
        "server/migrations",
        "server/tests",
        "doc",
        ".agents/skills",
    )
    for name in folders:
        paths.extend((project / name).rglob("*"))
    return {
        path.relative_to(project).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
        if path.is_file()
        and not path.is_symlink()
        and path.suffix in {".py", ".md", ".json", ".toml", ".txt", ".lock", ".html", ".js", ".css"}
        and not any(
            part in {"__pycache__", ".venv", "out", "var", "temp", "sources"}
            for part in path.relative_to(project).parts
        )
    }


def contract_digest(catalog: Catalog, modules: list[str] | None = None) -> str:
    declarations = [
        {
            "name": binding.contract.name,
            "input": binding.contract.input.model_json_schema(),
            "output": binding.contract.output.model_json_schema(),
            "access": binding.contract.access,
            "effect": binding.contract.effect,
            "entry": binding.contract.entry,
            "timeout": binding.contract.timeout,
            "audit": binding.contract.audit,
            "stream": binding.contract.stream,
            "errors": [error.code for error in binding.contract.errors],
            "query_budget": asdict(binding.contract.query_budget)
            if binding.contract.query_budget
            else None,
            "kind": binding.module.kind,
            "read_dependencies": binding.module.read_dependencies,
            "calls": catalog.links().get(binding.module.name, {}),
        }
        for binding in sorted(catalog.bindings.values(), key=lambda value: value.contract.name)
        if modules is None or binding.module.name in modules
    ]
    return hashlib.sha256(json.dumps(declarations, sort_keys=True).encode()).hexdigest()


def branch_name(project: Path) -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"
