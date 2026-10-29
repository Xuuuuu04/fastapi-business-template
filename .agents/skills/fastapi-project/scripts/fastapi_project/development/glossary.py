from pathlib import Path
from typing import Literal

from fastapi_project.development.check_assets import atomic_bytes
from fastapi_project.development.ledger_lock import serialized
from fastapi_project.development.plan import read_plan
from pydantic import BaseModel, ConfigDict, Field

from shared.modules.catalog import Catalog


class BusinessTerm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    word: str = Field(min_length=1, max_length=100)
    definition: str = Field(min_length=1, max_length=2000)
    aliases: list[str] = Field(default_factory=list)
    module: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    operations: list[str] = Field(min_length=1)


class BusinessGlossary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    terms: list[BusinessTerm] = Field(default_factory=list)

    def validate_terms(self) -> None:
        seen: set[str] = set()
        for term in self.terms:
            names = {word.strip().casefold() for word in [term.word, *term.aliases]}
            if not all(names) or names & seen or len(names) != 1 + len(term.aliases):
                raise ValueError("业务词或别名重复，先统一含义与负责包")
            if any(not name.startswith(term.module + ".") for name in term.operations):
                raise ValueError("业务词必须关联负责包自己的公开操作")
            seen |= names


def read_glossary(project: Path) -> BusinessGlossary:
    path = project / "doc/glossary.json"
    glossary = (
        BusinessGlossary.model_validate_json(path.read_bytes())
        if path.exists()
        else BusinessGlossary()
    )
    glossary.validate_terms()
    return glossary


@serialized
def add_term(project: Path, term: BusinessTerm) -> None:
    glossary = read_glossary(project)
    glossary.terms.append(term)
    glossary.validate_terms()
    atomic_bytes(
        project / "doc/glossary.json", (glossary.model_dump_json(indent=2) + "\n").encode()
    )


def match_terms(project: Path, query: str) -> list[BusinessTerm]:
    return [
        term
        for term in read_glossary(project).terms
        if any(query.casefold() in name.casefold() for name in [term.word, *term.aliases])
    ]


def target_problems(project: Path, catalog: Catalog) -> list[str]:
    plan = read_plan(project)
    targets = set(catalog.by_name)
    if plan:
        targets |= {
            f"{package['module']}.{name}"
            for line in plan["lines"]
            for package in line["packages"]
            for name in package["operations"]
        }
    return [
        f"业务词 {term.word} 引用未登记且未计划的操作 {name}"
        for term in read_glossary(project).terms
        for name in term.operations
        if name not in targets
    ]
