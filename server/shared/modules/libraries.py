"""
纯工具包的声明与静态依赖，共享数据与协议不需要数据库业务操作。
"""

import ast
import json
import keyword
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shared.errors.framework import DeclarationError


# 导出名称和业务含义由定位、依赖图与文档共同读取。
@dataclass(frozen=True)
class LibrarySpec:
    name: str
    title: str
    exports: tuple[str, ...]
    aliases: tuple[str, ...] = ()

    # 只描述声明，不调用工具函数。
    def shape(self) -> dict[str, Any]:
        return dict(
            name=self.name,
            title=self.title,
            kind="library",
            exports=list(self.exports),
            aliases=list(self.aliases),
        )


# 只读取包内静态描述，拒绝链接和不一致归属。
def library_specs(root: Path) -> list[LibrarySpec]:
    result = []
    for folder in sorted((root / "library").glob("*/")):
        if folder.name == "__pycache__":
            continue
        marker = folder / "module.json"
        if folder.is_symlink() or marker.is_symlink() or not marker.is_file():
            raise DeclarationError([f"工具包 {folder.name} 缺少安全的module.json"])
        raw = json.loads(marker.read_text())
        if not isinstance(raw, dict):
            raise DeclarationError([f"工具包 {folder.name} 的声明必须为对象"])
        if (raw.get("schema_version"), raw.get("kind"), raw.get("name")) != (
            2,
            "library",
            folder.name,
        ):
            raise DeclarationError([f"工具包 {folder.name} 的声明无效"])
        exports = export_names(raw, folder)
        values = raw.get("aliases", [])
        if not isinstance(values, list) or any(
            not isinstance(item, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", item)
            for item in values
        ):
            raise DeclarationError([f"工具包 {folder.name} 的别名无效"])
        aliases = tuple(values)
        result.append(LibrarySpec(folder.name, raw["title"], exports, aliases))
    return result


# 数据类允许大写名称；错误字段类型与重复导出明确报告，不执行公开入口。
def export_names(raw: dict[str, Any], folder: Path) -> tuple[str, ...]:
    values = raw.get("exports")
    if (
        not isinstance(values, list)
        or not values
        or not all(
            isinstance(name, str) and name.isidentifier() and not keyword.iskeyword(name)
            for name in values
        )
    ):
        raise DeclarationError([f"工具包 {folder.name} 必须声明有效且不重复的导出"])
    if len(set(values)) != len(values):
        raise DeclarationError([f"工具包 {folder.name} 必须声明有效且不重复的导出"])
    if not re.fullmatch(r"[a-z][a-z0-9]*(_[a-z0-9]+)*", folder.name):
        raise DeclarationError([f"工具包 {folder.name} 的目录名称无效"])
    if not isinstance(raw.get("title"), str) or not raw["title"].strip():
        raise DeclarationError([f"工具包 {folder.name} 的业务名称不能为空"])
    if (folder.parent.parent / "service" / folder.name).exists():
        raise DeclarationError([f"工具包 {folder.name} 与业务包同名"])
    return tuple(values)


# 静态导入只记录工具包名称，内部文件不成为跨包入口。
def imported_libraries(folder: Path) -> set[str]:
    found = set()
    for path in folder.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            for name in names:
                parts = name.split(".")
                if len(parts) >= 2 and parts[0] == "library":
                    found.add(parts[1])
    return found


# 实际依赖来自导入，计划不覆盖这些事实。
def library_links(root: Path) -> dict[str, list[str]]:
    names = {spec.name for spec in library_specs(root)}
    result = {name: sorted(imported_libraries(root / "library" / name) - {name}) for name in names}
    result.update(
        {
            folder.name: sorted(imported_libraries(folder))
            for folder in (root / "service").glob("*/")
            if folder.name != "__pycache__"
        }
    )
    return result


# 缺失目标与循环明确失败，传递依赖没有人为的三层限制。
def library_closure(name: str, links: dict[str, list[str]], names: set[str]) -> set[str]:
    found: set[str] = set()
    pending = list(links.get(name, []))
    while pending:
        target = pending.pop()
        if target not in names:
            raise DeclarationError([f"工具依赖 {target} 没有登记"])
        if target == name:
            raise DeclarationError([f"工具包 {name} 存在循环依赖"])
        if target not in found:
            found.add(target)
            pending.extend(links.get(target, []))
    return found
