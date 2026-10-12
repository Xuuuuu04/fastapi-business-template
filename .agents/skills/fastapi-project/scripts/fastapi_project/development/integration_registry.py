"""
登记与路由从合并后的包和已有公开绑定重生成，含独立逻辑的登记文件不覆盖。
"""

import ast
import json
import keyword
from pathlib import Path

from fastapi_project.development.check_assets import atomic_bytes
from fastapi_project.development.versions import catalog_bindings, route_ownership


# 包与接口标识只能用Python名称，不能通过登记内容插入任意代码。
def name_checked(name: str) -> str:
    if not name.isidentifier() or keyword.iskeyword(name):
        raise ValueError("派生登记包含非法名称")
    return name


# 只有导入、文档与明确MODULES列表属于派生登记，其他代码需要显式处理。
def catalog_names(source: str) -> set[str]:
    bindings = catalog_bindings(source)
    if bindings is None:
        raise ValueError("业务登记不是可重生成的静态清单")
    for node in ast.parse(source).body:
        if isinstance(node, ast.ImportFrom):
            if (
                node.module == "shared.modules.module"
                and all(alias.name == "Module" for alias in node.names)
                or node.module
                and node.module.startswith("service.")
                and node.module.endswith(".module")
                and all(alias.name == "module" for alias in node.names)
            ):
                continue
            raise ValueError("业务登记包含独立导入逻辑，不能直接重生成")
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            continue
        if isinstance(node, ast.AnnAssign | ast.Assign):
            target = node.target if isinstance(node, ast.AnnAssign) else node.targets[0]
            if isinstance(target, ast.Name) and target.id == "MODULES":
                continue
        raise ValueError("业务登记包含独立逻辑，不能直接重生成")
    return set(bindings)


# 旧包显式登记仍保留，新包自身module.json参与清单，未定义实现不能伪造启用。
def regenerate_catalog(project: Path, sources: list[str]) -> Path:
    names = set.union(*(catalog_names(source) for source in sources))
    for path in (project / "server/service").glob("*/module.json"):
        if path.is_symlink() or json.loads(path.read_text()).get("module") != path.parent.name:
            raise ValueError("包结构声明与目录不符")
        names.add(path.parent.name)
    for name in names:
        name_checked(name)
        if not (project / "server/service" / name / "module.py").is_file():
            raise ValueError("登记包缺少实际module.py：" + name)
    imports = "".join(
        f"from service.{name}.module import module as {name}\n" for name in sorted(names)
    )
    text = (
        '"""\n模块清单由业务包声明生成，新增与删除后重新生成。\n"""\n\n'
        + imports
        + "from shared.modules.module import Module\n\n"
        + "MODULES: list[Module] = [\n"
        + "".join(f"    {name},\n" for name in sorted(names))
        + "]\n"
    )
    target = project / "server/app/setup/catalog.py"
    atomic_bytes(target, text.encode())
    return target


# 只移除业务导入与业务字典，系统接口及自定义逻辑用语法结构逐项比较。
def router_core(source: str) -> tuple[str, dict[str, list[str]]]:
    mapping = route_ownership(source)
    if mapping is None:
        raise ValueError("路由登记不是明确静态清单")
    stems = {stem for values in mapping.values() for stem in values}
    lines = source.splitlines(keepends=True)
    edits = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "MODULE_ROUTERS"
            for target in node.targets
        ):
            raise ValueError("路由登记必须使用标准类型声明，不能直接重生成")
        if isinstance(node, ast.ImportFrom) and node.module == "app.api.v1":
            kept = [alias for alias in node.names if alias.name not in stems]
            replacement = (
                ast.unparse(ast.ImportFrom(module=node.module, names=kept, level=0)) + "\n"
                if kept
                else ""
            )
            edits.append((node.lineno - 1, node.end_lineno, replacement))
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "MODULE_ROUTERS"
        ):
            value = node.value
            if value is None:
                raise ValueError("路由登记缺少明确值")
            if any(
                isinstance(item, ast.Attribute) and item.attr != "router"
                for item in ast.walk(value)
            ):
                raise ValueError("自定义路由属性不能改写为默认router")
            edits.append(
                (
                    node.lineno - 1,
                    node.end_lineno,
                    "MODULE_ROUTERS: dict[str, tuple[APIRouter, ...]] = {}\n",
                )
            )
    for start, end, replacement in sorted(edits, reverse=True):
        lines[start:end] = [replacement]
    return "".join(lines), mapping


# 系统路由两边变更不猜取舍；业务路由按真正绑定的接口文件合并。
def regenerate_routers(project: Path, sources: list[str]) -> Path:
    cores = [router_core(source) for source in sources]
    shapes = [ast.dump(ast.parse(core), include_attributes=False) for core, _ in cores]
    if len(set(shapes)) != 1:
        raise ValueError("系统路由或独立逻辑变更需要处理后再整合")
    mappings: dict[str, set[str]] = {}
    for _, mapping in cores:
        for name, stems in mapping.items():
            mappings.setdefault(name, set()).update(stems)
    imports = sorted({name_checked(stem) for stems in mappings.values() for stem in stems})
    text = cores[0][0]
    entries = "".join(
        f"    {name!r}: ({''.join(stem + '.router,' for stem in sorted(stems))}),\n"
        for name, stems in sorted(mappings.items())
    )
    text = text.replace(
        "MODULE_ROUTERS: dict[str, tuple[APIRouter, ...]] = {}",
        "MODULE_ROUTERS: dict[str, tuple[APIRouter, ...]] = {\n" + entries + "}",
    )
    text = text.replace(
        "ROUTERS: list[APIRouter]",
        "".join(f"from app.api.v1 import {stem}\n" for stem in imports)
        + "\nROUTERS: list[APIRouter]",
        1,
    )
    target = project / "server/app/api/routers.py"
    atomic_bytes(target, text.encode())
    return target
