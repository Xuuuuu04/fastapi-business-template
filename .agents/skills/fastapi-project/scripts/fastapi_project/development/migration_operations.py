"""
新增分支DDL按表、列和命名对象分析，未知SQL或动态操作不能当作独立迁移。
"""

import ast
from dataclasses import dataclass

from fastapi_project.development.migration_graph import Revision


# 对象读写足迹用于跨分支比较，星号表示整个表，不证明业务数据已经验收。
@dataclass(frozen=True)
class Touch:
    table: str
    object: str
    access: str
    source: str


# 字符串和字符串列表必须是常量，变量或执行表达式留给人工检查。
def literal(node: ast.AST | None) -> object:
    try:
        return ast.literal_eval(node) if node is not None else None
    except (ValueError, TypeError) as error:
        raise ValueError("DDL参数不是静态常量") from error


# 完整常量标识不能为空，None不能被转成一个虚假的表名。
def identifier(node: ast.AST | None) -> str:
    value = literal(node)
    if not isinstance(value, str) or not value:
        raise ValueError("DDL对象名称不是明确字符串")
    return value


# 明确schema参与对象身份，跨schema对象和外键引用不混作默认表。
def qualified(name: str, call: ast.Call) -> str:
    schema = next((keyword.value for keyword in call.keywords if keyword.arg == "schema"), None)
    if schema is None or literal(schema) is None:
        return name
    return identifier(schema) + "." + name


# 列改动包含新旧名字，计算表达式按整表依赖处理。
def column_operation(call: ast.Call, table: str | None, source: str) -> list[Touch]:
    if not isinstance(call.func, ast.Attribute):
        raise ValueError("列操作需要明确方法")
    name = call.func.attr
    target = table or qualified(identifier(call.args[0]), call)
    field = call.args[0] if table else call.args[1]
    column = (
        identifier(field.args[0])
        if name == "add_column" and isinstance(field, ast.Call)
        else identifier(field)
    )
    result = [Touch(target, "column:" + column, "write", source)]
    for keyword in call.keywords:
        if keyword.arg == "new_column_name":
            result.append(Touch(target, "column:" + identifier(keyword.value), "write", source))
    if any(isinstance(node, ast.Attribute) and node.attr == "Computed" for node in ast.walk(call)):
        result.append(Touch(target, "*", "read", source))
    return result


# 命名对象既锁定名称，也保留依赖列，跨分支新列与索引不是独立操作。
def named_operation(call: ast.Call, table: str | None, source: str) -> list[Touch]:
    if not isinstance(call.func, ast.Attribute):
        raise ValueError("命名对象操作需要明确方法")
    name = call.func.attr
    keywords = {keyword.arg: keyword.value for keyword in call.keywords}
    target = table or qualified(
        identifier(call.args[1] if len(call.args) > 1 else keywords.get("table_name")), call
    )
    node = call.args[0]
    identity = identifier(node.args[0] if isinstance(node, ast.Call) else node)
    kind = "index:" if "index" in name else "constraint:"
    result = [Touch(target, kind + identity, "write", source)]
    if "index" in name:
        namespace = target.rpartition(".")[0]
        result.append(
            Touch(namespace + ".@indexes" if namespace else "@indexes", identity, "write", source)
        )
    if name.startswith("create_"):
        columns = literal(call.args[1] if table else call.args[2])
        if isinstance(columns, list | tuple) and all(isinstance(column, str) for column in columns):
            result += [Touch(target, "column:" + column, "read", source) for column in columns]
        else:
            result.append(Touch(target, "*", "read", source))
    return result


# 已知Alembic动作分流到局部分析，原始SQL和未覆盖动作明确要求处理。
def operation(call: ast.Call, table: str | None, source: str) -> list[Touch]:
    if not isinstance(call.func, ast.Attribute):
        raise ValueError("DDL调用不是明确方法")
    name = call.func.attr
    if name == "f":
        return []
    if name in {"create_table", "drop_table", "rename_table"}:
        names = [identifier(call.args[0])]
        if name == "rename_table":
            names.append(identifier(call.args[1]))
        return [Touch(qualified(value, call), "*", "write", source) for value in names]
    if name in {"add_column", "drop_column", "alter_column"}:
        return column_operation(call, table, source)
    if name in {
        "create_index",
        "drop_index",
        "create_unique_constraint",
        "create_primary_key",
        "drop_constraint",
        "create_check_constraint",
    }:
        return named_operation(call, table, source)
    raise ValueError("尚未支持的DDL操作：" + name)


# 外键参数产生实际读取足迹，引用别的分支新表必须声明依赖，不能任由版本号排序。
def foreign_references(function: ast.FunctionDef, path: str) -> list[Touch]:
    result = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"ForeignKey", "ForeignKeyConstraint"}:
            continue
        references = (
            [identifier(node.args[0])] if node.func.attr == "ForeignKey" else literal(node.args[1])
        )
        if not isinstance(references, list | tuple) or any(
            not isinstance(value, str) or "." not in value for value in references
        ):
            raise ValueError("外键目标不明确")
        for value in references:
            table, _, column = value.rpartition(".")
            result.append(Touch(table, "column:" + column, "read", f"{path}:{node.lineno}"))
    return result


# batch表来自明确的with上下文，其他上下文管理器不冒充数据库批量操作。
def contexts(function: ast.FunctionDef) -> tuple[dict[str, str | None], list[str]]:
    aliases: dict[str, str | None] = {"op": None}
    unknown = []
    for node in ast.walk(function):
        if isinstance(node, ast.If | ast.For | ast.While | ast.Try | ast.AsyncFor):
            unknown.append("含动态控制流程")
        if not isinstance(node, ast.With):
            continue
        for item in node.items:
            call = item.context_expr
            if (
                not isinstance(call, ast.Call)
                or not isinstance(call.func, ast.Attribute)
                or call.func.attr != "batch_alter_table"
                or not isinstance(item.optional_vars, ast.Name)
            ):
                unknown.append("含未知操作上下文")
                continue
            aliases[item.optional_vars.id] = qualified(identifier(call.args[0]), call)
    return aliases, unknown


# 仅允许类型构造表达式，绑定连接、未知模块方法和帮助函数都需要实际人工分析。
def known_constructor(call: ast.Call) -> bool:
    node = call.func
    while isinstance(node, ast.Attribute):
        node = node.value
    return isinstance(node, ast.Name) and node.id in {"sa", "sqlalchemy"}


# 一个upgrade中的确定调用与疑问分别返回，不能用确定的部分掩盖未知SQL。
def analyze(revision: Revision) -> tuple[list[Touch], list[str]]:
    upgrades = [
        node
        for node in revision.tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade"
    ]
    if len(upgrades) != 1:
        return [], [revision.id + "缺少唯一upgrade函数"]
    function = upgrades[0]
    try:
        aliases, unknown = contexts(function)
        touches = foreign_references(function, revision.path.name)
    except (ValueError, IndexError) as error:
        return [], [revision.id + "：" + str(error)]
    for node in (node for node in ast.walk(function) if isinstance(node, ast.Call)):
        source = f"{revision.path.name}:{node.lineno}"
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in aliases
        ):
            if node.func.attr == "batch_alter_table":
                continue
            try:
                touches += operation(node, aliases[node.func.value.id], source)
            except (ValueError, IndexError) as error:
                unknown.append(source + "：" + str(error))
        elif not known_constructor(node):
            unknown.append(source + "：使用无法静态证明的帮助函数或绑定调用")
    return touches, sorted(set(unknown))
