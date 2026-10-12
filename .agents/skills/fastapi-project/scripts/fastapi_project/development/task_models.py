"""
任务卡记录范围、阅读资料与基线，不调度代理，也不声称文件摘要能验证操作者身份。
"""

import hashlib
import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from fastapi_project.development.check_assets import atomic_bytes
from pydantic import BaseModel, ConfigDict, Field

from shared.modules.catalog import Catalog


# 本机任务卡含明确范围和完成条件，检查证据另外引用不复制敏感轨迹。
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


# 任务文件只放固定本机目录，编号不能作为任意路径读写入口。
def card_path(project: Path, identity: str) -> Path:
    if len(identity) != 32 or any(letter not in "0123456789abcdef" for letter in identity):
        raise ValueError("任务编号不合法")
    return project / ".agents/records/tasks" / (identity + ".json")


# 一次替换整张卡，退出时不会留下半份完成状态。
def save_card(project: Path, card: TaskCard) -> None:
    atomic_bytes(card_path(project, card.id), (card.model_dump_json(indent=2) + "\n").encode())


# 当前卡按原件读取，不能靠面板颜色反向填完成状态。
def read_card(project: Path, identity: str) -> TaskCard:
    return TaskCard.model_validate_json(card_path(project, identity).read_bytes())


# 基线仅列源码、迁移和脱敏开发文档，不读.env、原话材料、数据库或运行目录。
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
        and path.suffix in {".py", ".md", ".json", ".toml", ".txt", ".lock"}
        and not any(
            part in {"__pycache__", ".venv", "out", "var", "temp", "sources"}
            for part in path.relative_to(project).parts
        )
    }


# 契约只含公开模型、权限与操作形态，修改实现不会让契约误过期。
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


# 当前分支只做说明，未初始化Git的产品明确为未知而非伪造main。
def branch_name(project: Path) -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"
