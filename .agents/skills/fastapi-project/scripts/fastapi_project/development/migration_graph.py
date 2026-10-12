"""
从迁移脚本静态读取版本图，不执行脚本；缺少声明、重复版本和循环明确失败。
"""

import ast
from dataclasses import dataclass
from pathlib import Path

from fastapi_template.template.files import safe_path


# 一个已有迁移版本与其真实源码、父版本，业务SQL尚未在分析阶段执行。
@dataclass(frozen=True)
class Revision:
    id: str
    parents: tuple[str, ...]
    dependencies: tuple[str, ...]
    path: Path
    tree: ast.Module


# 只接受Python常量声明，动态版本号不能被猜成可安全合并的图。
def declarations(tree: ast.Module) -> dict:
    result = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign | ast.AnnAssign):
            continue
        target = (
            node.target
            if isinstance(node, ast.AnnAssign)
            else node.targets[0]
            if isinstance(node, ast.Assign) and len(node.targets) == 1
            else None
        )
        if isinstance(target, ast.Name) and target.id in {
            "revision",
            "down_revision",
            "depends_on",
        }:
            if node.value is None:
                raise ValueError("迁移版本声明缺少值")
            try:
                result[target.id] = ast.literal_eval(node.value)
            except (ValueError, TypeError) as error:
                raise ValueError("迁移版本声明必须为静态常量") from error
    return result


# 父版本和声明依赖都是图约束，空父表示初始版本。
def revision_refs(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    values = (value,) if isinstance(value, str) else value
    if not isinstance(values, tuple | list) or any(
        not isinstance(item, str) or not item for item in values
    ):
        raise ValueError("迁移父版本格式不支持")
    return tuple(values)


# 读取普通源码文件，拒绝链接、遗漏父声明和重复版本。
def read_graph(project: Path) -> dict[str, Revision]:
    graph = {}
    for path in sorted(safe_path(project, "server/migrations/versions").glob("*.py")):
        if path.is_symlink():
            raise ValueError("迁移文件不能是链接")
        tree = ast.parse(path.read_text())
        fields = declarations(tree)
        identity = fields.get("revision")
        if not isinstance(identity, str) or not identity or "down_revision" not in fields:
            raise ValueError("迁移缺少静态版本声明：" + path.name)
        if identity in graph:
            raise ValueError("迁移版本重复：" + identity)
        parents = revision_refs(fields["down_revision"])
        graph[identity] = Revision(
            identity, parents, revision_refs(fields.get("depends_on")), path, tree
        )
    for identity in graph:
        ancestors(graph, identity)
    return graph


# 深度优先保留路径，版本循环不能被已访问集合悄悄略过。
def ancestors(graph: dict[str, Revision], identity: str, trail: tuple[str, ...] = ()) -> set[str]:
    if identity not in graph:
        raise ValueError("迁移父版本不存在：" + identity)
    if identity in trail:
        raise ValueError("迁移版本形成循环：" + identity)
    found = {identity}
    for parent in (*graph[identity].parents, *graph[identity].dependencies):
        found |= ancestors(graph, parent, (*trail, identity))
    return found


# 多头必须有唯一最近共同祖先，互不相关的迁移历史不能自动拼接。
def branches(graph: dict[str, Revision]) -> tuple[list[str], str | None, dict[str, list[Revision]]]:
    parents = {parent for revision in graph.values() for parent in revision.parents}
    heads = sorted(graph.keys() - parents)
    if len(heads) <= 1:
        return heads, None, {}
    paths = {head: ancestors(graph, head) for head in heads}
    common = set.intersection(*paths.values())
    nearest = common - {prior for name in common for prior in ancestors(graph, name) - {name}}
    if len(nearest) != 1:
        raise ValueError("多头迁移没有唯一最近共同版本，请先整理版本图")
    anchor = nearest.pop()
    base = ancestors(graph, anchor)
    return (
        heads,
        anchor,
        {head: [graph[name] for name in sorted(path - base)] for head, path in paths.items()},
    )
