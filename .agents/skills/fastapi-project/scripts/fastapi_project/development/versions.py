"""
总登记文件的读取与中性化：从模块目录和模块路由登记读出每个模块拥有的接口文件，
并把登记清单从公共代码摘要中分离，新增模块不再使全部旧模块的检查过期。
"""

import ast
from pathlib import Path

# 版本计算跳过的缓存目录；修改、增加、删除业务文件都会改变结果。
EXCLUDED = {"__pycache__", ".venv", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
# 模块自己的接口文件目录，以及路由登记引用它时使用的导入模块名。
V1_FOLDER = "app/api/v1"
V1_IMPORT = "app.api.v1"
ROUTERS_FILE = "app/api/routers.py"
# 两份总登记（模块目录、模块路由）：登记清单本身与只供登记使用的导入不算公共变化，
# 新增模块不再使全部旧模块的检查过期；每个模块自己的声明在 service/<模块>/module.py，
# 已随模块路径参与版本。登记文件里登记之外的部分（系统路由、创建函数）仍算公共代码。
REGISTRATIONS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "app/setup/catalog.py": (("MODULES",), ("service.",)),
    ROUTERS_FILE: (("MODULE_ROUTERS",), (V1_IMPORT,)),
}


# 一轮版本计算内的读取缓存：目录只列举一次，文件只读一次，不随模块数量重复。
class Reader:
    # 记录列举、原始内容和文本内容三份缓存。
    def __init__(self) -> None:
        self.files: dict[tuple[Path, Path], list[Path]] = {}
        self.contents: dict[Path, bytes | None] = {}
        self.sources: dict[Path, str | None] = {}

    # 列出路径下参与版本的文件；目录展开并跳过缓存目录，不存在的路径没有文件。
    def files_under(self, path: Path, root: Path) -> list[Path]:
        if (path, root) not in self.files:
            self.files[(path, root)] = (
                [path]
                if path.is_file()
                else [
                    item
                    for item in path.rglob("*")
                    if item.is_file() and not EXCLUDED.intersection(item.relative_to(root).parts)
                ]
            )
        return self.files[(path, root)]

    # 读原始内容；文件不存在时返回 None，由调用方决定如何处理。
    def read(self, path: Path) -> bytes | None:
        if path not in self.contents:
            self.contents[path] = path.read_bytes() if path.is_file() else None
        return self.contents[path]

    # 读文本内容；不存在或不是 UTF-8 时返回 None，由调用方退回原始内容。
    def source(self, path: Path) -> str | None:
        if path not in self.sources:
            content = self.read(path)
            try:
                self.sources[path] = content.decode("utf-8") if content is not None else None
            except UnicodeDecodeError:
                self.sources[path] = None
        return self.sources[path]


# 直接赋值语句的赋值目标；覆盖带类型标注的登记写法。
def _targets_of(node: ast.stmt) -> list[ast.expr]:
    if isinstance(node, ast.Assign):
        return list(node.targets)
    if isinstance(node, ast.AnnAssign):
        return [node.target]
    return []


# 是否对指定名字的直接赋值。
def _is_registration(node: ast.stmt, names: tuple[str, ...]) -> bool:
    return any(isinstance(item, ast.Name) and item.id in names for item in _targets_of(node))


# 找到对指定名字的直接赋值并返回它的值；没有时返回 None。
def _registration_value(body: list[ast.stmt], names: tuple[str, ...]) -> ast.expr | None:
    if sum(_is_registration(node, names) for node in body) != 1:
        return None
    for node in body:
        if (
            _is_registration(node, names)
            and isinstance(node, ast.Assign | ast.AnnAssign)
            and node.value is not None
        ):
            return node.value
    return None


# 只供登记清单使用的导入按名去掉，整条都只供登记时删除；其余语句规范化保留。
def _kept_statement(node: ast.stmt, used: set[str], prefixes: tuple[str, ...]) -> str | None:
    if not (
        isinstance(node, ast.ImportFrom)
        and node.module is not None
        and any(node.module.startswith(prefix) for prefix in prefixes)
    ):
        return ast.unparse(node)
    kept = [alias for alias in node.names if (alias.asname or alias.name).split(".")[0] in used]
    if not kept:
        return None
    if len(kept) == len(node.names):
        return ast.unparse(node)
    return ast.unparse(ast.ImportFrom(module=node.module, names=kept, level=node.level))


# 登记文件去掉登记清单与只供登记使用的导入后的剩余公共部分；
# 解析不了时返回 None，调用方退回原始内容，宁可多失效也不漏。
def _registration_rest(
    source: str, names: tuple[str, ...], prefixes: tuple[str, ...]
) -> str | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    if (names == ("MODULES",) and catalog_bindings(source) is None) or (
        names == ("MODULE_ROUTERS",) and route_ownership(source) is None
    ):
        return None
    body = [node for node in tree.body if not _is_registration(node, names)]
    used = {
        item.id
        for node in body
        for item in ast.walk(node)
        if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Load)
    }
    return "\n".join(
        text for node in body if (text := _kept_statement(node, used, prefixes)) is not None
    )


# 登记文件参与公共摘要的内容：剩余公共部分；解析不了时用原始内容，缺失时用占位记录。
def registration_entry(
    reader: Reader, path: Path, names: tuple[str, ...], prefixes: tuple[str, ...]
) -> bytes:
    source = reader.source(path)
    if source is not None:
        rest = _registration_rest(source, names, prefixes)
        if rest is not None:
            return rest.encode("utf-8")
    return reader.read(path) or b"<missing>"


# MODULE_ROUTERS 一项绑定的接口文件名；引用解析不了时返回 None。
def _router_stems(element: ast.expr, aliases: dict[str, str]) -> list[str] | None:
    items = element.elts if isinstance(element, ast.Tuple) else [element]
    stems = []
    for item in items:
        if not (isinstance(item, ast.Attribute) and isinstance(item.value, ast.Name)):
            return None
        stem = aliases.get(item.value.id)
        if stem is None:
            return None
        stems.append(stem)
    return stems


# 从路由登记读取每个模块绑定的接口文件名；登记不是静态字面量时返回 None，
# 调用方把全部接口文件保守地算作公共代码。
def route_ownership(source: str | None) -> dict[str, list[str]] | None:
    if source is None:
        return None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    value = _registration_value(tree.body, ("MODULE_ROUTERS",))
    if not isinstance(value, ast.Dict):
        return None
    aliases = {
        alias.asname or alias.name: alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == V1_IMPORT
        for alias in node.names
    }
    mapping: dict[str, list[str]] = {}
    for key, element in zip(value.keys, value.values, strict=True):
        if (
            not (isinstance(key, ast.Constant) and isinstance(key.value, str))
            or key.value in mapping
        ):
            return None
        stems = _router_stems(element, aliases)
        if stems is None:
            return None
        mapping[key.value] = sorted(stems)
    return mapping


# 总目录按导入的业务包归属，同时保留真正绑定的导入名称，替换实现不能沿用旧检查。
def catalog_bindings(source: str) -> dict[str, str] | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    value = _registration_value(tree.body, ("MODULES",))
    if not isinstance(value, ast.List | ast.Tuple):
        return None
    aliases = {
        alias.asname or alias.name: (node.module.split(".")[1], node.module, alias.name)
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.level == 0
        and node.module is not None
        and node.module.startswith("service.")
        for alias in node.names
    }
    result = {}
    for item in value.elts:
        if not isinstance(item, ast.Name) or item.id not in aliases:
            return None
        name, module, imported_name = aliases[item.id]
        if name in result:
            return None
        result[name] = f"{module}:{imported_name}:{ast.dump(item)}"
    return result


# 路由归属之外还记录属性与绑定表达式；同文件 router 改为 other_router 也要过期。
def router_bindings(source: str) -> dict[str, str] | None:
    ownership = route_ownership(source)
    if ownership is None:
        return None
    tree = ast.parse(source)
    value = _registration_value(tree.body, ("MODULE_ROUTERS",))
    if not isinstance(value, ast.Dict):
        return None
    return {
        key.value: ast.dump(element)
        for key, element in zip(value.keys, value.values, strict=True)
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }


# 两份登记的各包部分单独计入版本；未知写法已由公共部分保守保留原始内容。
def registration_parts(reader: Reader, project: Path) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for relative in REGISTRATIONS:
        source = reader.source(project / "server" / relative)
        if source is None:
            continue
        bindings = catalog_bindings(source) if relative != ROUTERS_FILE else router_bindings(source)
        for name, text in (bindings or {}).items():
            result[name] = result.get(name, b"") + relative.encode() + b"\0" + text.encode() + b"\0"
    return result


# 每个模块在 app/api/v1 下自己拥有的接口文件；读不出静态归属时返回 None。
def module_api_files(project: Path) -> dict[str, list[Path]] | None:
    reader = Reader()
    stems = route_ownership(reader.source(project / "server" / ROUTERS_FILE))
    if stems is None:
        return None
    folder = project / "server" / V1_FOLDER
    return {name: [folder / f"{stem}.py" for stem in names] for name, names in stems.items()}
