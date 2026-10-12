"""
业务词表显式登记定义、别名与负责操作；没有登记的含义保持未知，不从函数名猜业务。
"""

from pathlib import Path
from typing import Literal

from fastapi_project.development.check_assets import atomic_bytes
from fastapi_project.development.ledger_lock import serialized
from fastapi_project.development.plan import read_plan
from pydantic import BaseModel, ConfigDict, Field

from shared.modules.catalog import Catalog


# 一个业务词只由一个包负责，可以关联多个本包公开操作。
class BusinessTerm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    word: str = Field(min_length=1, max_length=100)
    definition: str = Field(min_length=1, max_length=2000)
    aliases: list[str] = Field(default_factory=list)
    module: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    operations: list[str] = Field(min_length=1)


# 空模板不创建虚构词表，词或别名重复也不能默默覆盖。
class BusinessGlossary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    terms: list[BusinessTerm] = Field(default_factory=list)

    # 词义归属明确且所有公开操作属于负责包，实际是否登记由项目检查另行核对。
    def validate_terms(self) -> None:
        seen: set[str] = set()
        for term in self.terms:
            names = {word.strip().casefold() for word in [term.word, *term.aliases]}
            if not all(names) or names & seen or len(names) != 1 + len(term.aliases):
                raise ValueError("业务词或别名重复，先统一含义与负责包")
            if any(not name.startswith(term.module + ".") for name in term.operations):
                raise ValueError("业务词必须关联负责包自己的公开操作")
            seen |= names


# 原件JSON为事实，检索不另建会过期的索引。
def read_glossary(project: Path) -> BusinessGlossary:
    path = project / "doc/glossary.json"
    glossary = (
        BusinessGlossary.model_validate_json(path.read_bytes())
        if path.exists()
        else BusinessGlossary()
    )
    glossary.validate_terms()
    return glossary


# 显式改词表保留Git变更，不自动从代码生成业务定义。
@serialized
def add_term(project: Path, term: BusinessTerm) -> None:
    glossary = read_glossary(project)
    glossary.terms.append(term)
    glossary.validate_terms()
    atomic_bytes(
        project / "doc/glossary.json", (glossary.model_dump_json(indent=2) + "\n").encode()
    )


# 定位先返回明确词义与负责操作，普通声明匹配仍作为另一类结果保留。
def match_terms(project: Path, query: str) -> list[BusinessTerm]:
    return [
        term
        for term in read_glossary(project).terms
        if any(query.casefold() in name.casefold() for name in [term.word, *term.aliases])
    ]


# 定义可先于实现存在，但操作必须已登记或明确列在计划里，拼错不能悄悄落空。
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
