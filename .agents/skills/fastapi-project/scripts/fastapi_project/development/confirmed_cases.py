import ast
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from fastapi_project.development.ledger_models import LedgerRule, RuleLedger
from fastapi_project.development.ledger_store import decode_ledger
from fastapi_project.development.ledger_store_models import parse_index
from pydantic import BaseModel, ConfigDict, Field


class CaseFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*\.R-\d+-C\d+$")
    input: dict[str, Any]
    initial: dict[str, Any]
    expected: dict[str, Any]
    observations: list[dict[str, Any]] = Field(default_factory=list)
    database: dict[str, Any] = Field(default_factory=dict)
    effects: dict[str, Any] = Field(default_factory=dict)
    assertions: list[str] = Field(min_length=1)
    tests: list[str] = Field(min_length=1)


def test_assertions(project: Path, nodeid: str) -> list[str]:
    path, separator, name = nodeid.partition("::")
    target = (project / "server" / path).resolve()
    if not separator or not target.is_relative_to((project / "server/tests").resolve()):
        raise ValueError("确认样例必须引用项目内的准确测试函数")
    tree = ast.parse(target.read_text())
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name
    ]
    if len(functions) != 1:
        raise ValueError(f"找不到准确测试函数 {nodeid}")
    statements = [ast.dump(node) for node in ast.walk(functions[0]) if isinstance(node, ast.Assert)]
    if not statements:
        raise ValueError(f"测试 {nodeid} 没有可保护的断言")
    return statements + assertion_inputs(functions[0])


def assertion_inputs(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    dependencies = {
        node.id
        for statement in ast.walk(function)
        if isinstance(statement, ast.Assert)
        for node in ast.walk(statement)
        if isinstance(node, ast.Name)
    }
    selected: list[ast.AST] = [*function.decorator_list, function.args]
    candidates = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Assign | ast.AnnAssign | ast.AugAssign | ast.NamedExpr)
    ]
    while True:
        needed = [
            node
            for node in candidates
            if any(
                isinstance(name, ast.Name)
                and isinstance(name.ctx, ast.Store)
                and name.id in dependencies
                for name in ast.walk(node)
            )
        ]
        if not needed:
            break
        selected.extend(needed)
        candidates = [node for node in candidates if node not in needed]
        dependencies |= {
            name.id for node in needed for name in ast.walk(node) if isinstance(name, ast.Name)
        }
    return [ast.dump(node) for node in selected]


def case_digest(project: Path, path: Path) -> tuple[str, str]:
    fixture = CaseFixture.model_validate_json(path.read_bytes())
    assertions = {test: test_assertions(project, test) for test in fixture.tests}
    payload = [fixture.model_dump(mode="json"), assertions]
    content = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    return fixture.id, hashlib.sha256(content).hexdigest()


def rule_cases(project: Path, rule: str) -> dict[str, str]:
    module = rule.split(".", 1)[0]
    found: dict[str, str] = {}
    for path in sorted((project / "doc" / module / "cases").glob("*.json")):
        identity, digest = case_digest(project, path)
        if identity.rsplit("-C", 1)[0] == rule:
            if identity in found:
                raise ValueError("确认样例编号重复")
            found[identity] = digest
        elif not identity.startswith(module + "."):
            raise ValueError("样例资料不属于本业务包")
    return found


def baseline(project: Path) -> RuleLedger | None:
    result = subprocess.run(
        ["git", "show", "HEAD:doc/rules-ledger.json"],
        cwd=project,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        return None
    index = parse_index(result.stdout)
    packages = {}
    for name in index.get("packages", []):
        if not isinstance(name, str) or not name.isidentifier():
            raise ValueError("Git基线规则包名不合法")
        content = subprocess.run(
            ["git", "show", f"HEAD:doc/{name}/rules.json"],
            cwd=project,
            capture_output=True,
            check=False,
        )
        if content.returncode:
            raise ValueError("Git基线的分包规则缺失")
        packages[name] = json.loads(content.stdout)
    return decode_ledger(index, packages)


def revision_problems(rule: LedgerRule, old: LedgerRule | None) -> list[str]:
    if old is None or old.state != "confirmed" or rule.case_digests == old.case_digests:
        return []
    if rule.revision <= old.revision:
        return [f"规则 {rule.id} 的确认样例摘要被改写，缺少新修订依据"]
    if rule.state != "confirmed":
        return []
    prior = {record.source for record in old.confirmations}
    accepted = any(
        record.revision == rule.revision
        and record.kind == "human_explicit"
        and record.source not in prior
        for record in rule.confirmations
    )
    return [] if accepted else [f"规则 {rule.id} 的新样例缺少新的原话确认依据"]


def current_problems(project: Path, rule: LedgerRule) -> list[str]:
    if rule.state != "confirmed":
        return []
    try:
        if rule_cases(project, rule.id) != rule.case_digests:
            return [f"规则 {rule.id} 的确认输入、预期或关键断言已经改变"]
    except (ValueError, OSError, SyntaxError) as error:
        return [f"规则 {rule.id} 的确认样例不可读取：{error}"]
    return []


def case_problems(project: Path, ledger: RuleLedger, *, delivery: bool = False) -> list[str]:
    previous = baseline(project)
    old = {rule.id: rule for rule in previous.rules} if previous else {}
    current = {rule.id: rule for rule in ledger.rules}
    problems = [
        f"已确认规则 {rule.id} 被删除，请保留废止与变更历史"
        for rule in old.values()
        if rule.state == "confirmed" and rule.id not in current
    ]
    for rule in ledger.rules:
        if delivery and rule.risk == "high" and rule.state not in {"confirmed", "retired"}:
            problems.append(f"高风险规则 {rule.id} 尚未明确确认")
        problems += revision_problems(rule, old.get(rule.id))
        problems += current_problems(project, rule)
    return problems
