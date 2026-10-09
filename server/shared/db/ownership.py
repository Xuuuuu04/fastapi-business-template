"""
迁移只维护登记的表；外部表保留，历史迁移按兼容配置提醒或拒绝。
"""

import ast
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import Table

from shared.config.settings import Settings
from shared.modules.module import Module

log = logging.getLogger("server.migrations")


# 归属来自明确的框架文件与模块登记，不按表名前缀推定权限。
@dataclass(frozen=True)
class TableOwnership:
    owned: frozenset[str]
    external: frozenset[str]

    # 已登记外部表仍不允许由本产品的迁移维护。
    def require_owned(self, table: str, action: str) -> None:
        if table not in self.owned:
            raise ValueError(
                f"拒绝{action}表 {table}：未登记为本产品维护的表。"
                "请在模块 tables 或 owned_tables / APP_OWNED_TABLES 登记归属；"
                "只保留的外部或历史表登记 external_tables / APP_EXTERNAL_TABLES。"
            )

    # Alembic反射对象：未知表拒绝，外部表忽略，登记表正常比较。
    def include_object(
        self, obj: Any, name: str, kind: str, reflected: bool, compare_to: Any
    ) -> bool:
        table = obj if kind == "table" else getattr(obj, "table", None)
        if table is None:
            return True
        key = table.key
        if key in self.external:
            return False
        self.require_owned(key, "自动比较或修改")
        return True


# 使用全部登记模块，关闭入口不意味着可以删除该模块的数据表。
def ownership(modules: Sequence[Module], settings: Settings) -> TableOwnership:
    import shared.access.audit as audit
    import shared.db.history as history
    import shared.jobs.tables as jobs
    import shared.operations.tables as operations
    import shared.pipelines.tables as pipelines
    import shared.records.tables as records

    owned = {
        value.key
        for source in (audit, history, jobs, operations, pipelines, records)
        for value in vars(source).values()
        if isinstance(value, Table)
    }
    owned.update(settings.owned_tables)
    external = set(settings.external_tables)
    for module in modules:
        owned.update(table.key for table in module.tables)
        owned.update(module.owned_tables)
        external.update(module.external_tables)
    overlap = owned & external
    if overlap:
        raise ValueError(f"表归属重复：{', '.join(sorted(overlap))} 同时登记为 owned 和 external")
    if any(not isinstance(name, str) or not name.strip() for name in owned | external):
        raise ValueError("表归属必须填写非空表名，含schema的表用 schema.table")
    return TableOwnership(frozenset(owned), frozenset(external))


# 不执行迁移源码；扫描升级和降级中的显式破坏动作、批量操作与原始SQL。
def migration_problems(folder: Path, tables: TableOwnership) -> list[str]:
    problems = []
    for path in sorted(folder.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as error:
            problems.append(f"{path.name}:{error.lineno}：迁移语法错误")
            continue
        batches = batch_tables(tree)
        aliases = operation_aliases(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            action = operation_name(node, aliases)
            if action not in (
                "drop_table",
                "rename_table",
                "alter_column",
                "drop_column",
                "execute",
            ):
                continue
            receiver = node.func.value if isinstance(node.func, ast.Attribute) else None
            batch = batches.get(receiver.id) if isinstance(receiver, ast.Name) else None
            table = batch or table_argument(node)
            if action == "execute":
                problems.append(
                    f"{path.name}:{node.lineno}：原始SQL迁移归属未知，请改用Alembic声明操作"
                )
            elif table not in tables.owned:
                problems.append(
                    f"{path.name}:{node.lineno}：{action} 表 {table} 未登记为owned；"
                    "在模块 tables/owned_tables 或 APP_OWNED_TABLES 登记；"
                    "external_tables仅保留，不能由迁移修改"
                )
    return problems


# Alembic操作直接导入或使用别名时仍按真实动作检查。
def operation_aliases(tree: ast.AST) -> dict[str, str]:
    return {
        item.asname or item.name: item.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "alembic.op"
        for item in node.names
    }


# 不认识的调用不推定安全；直接SQL调用也保持未知。
def operation_name(call: ast.Call, aliases: dict[str, str]) -> str:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    if isinstance(call.func, ast.Name):
        return aliases.get(call.func.id, "")
    return ""


# 批量迁移的内部调用沿用with里登记的原表名。
def batch_tables(tree: ast.AST) -> dict[str, str]:
    batches = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.With):
            continue
        for item in node.items:
            call = item.context_expr
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "batch_alter_table"
                and isinstance(item.optional_vars, ast.Name)
            ):
                batches[item.optional_vars.id] = table_argument(call)
    return batches


# 位置参数和命名参数都识别；无法静态确认的名称保持未知。
def table_argument(call: ast.Call) -> str:
    names = {item.arg: item.value for item in call.keywords}
    value = names.get("table_name", call.args[0] if call.args else None)
    table = (
        value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else "未知"
    )
    schema = names.get("schema")
    if isinstance(schema, ast.Constant) and isinstance(schema.value, str) and schema.value:
        table = f"{schema.value}.{table}"
    return table


# 旧产品先提醒，明确启用严格模式后同一问题成为错误。
def check_migrations(root: Path, modules: Sequence[Module], settings: Settings) -> list[str]:
    tables = ownership(modules, settings)
    problems = migration_problems(root / "migrations" / "versions", tables)
    if settings.migration_strict:
        return problems
    for problem in problems:
        log.warning("迁移兼容提醒：%s；整理后开启 APP_MIGRATION_STRICT=true", problem)
    return []
