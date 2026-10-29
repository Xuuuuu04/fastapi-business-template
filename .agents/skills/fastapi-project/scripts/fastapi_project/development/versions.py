import ast
from pathlib import Path

EXCLUDED = {"__pycache__", ".venv", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
V1_FOLDER = "app/api/v1"
V1_IMPORT = "app.api.v1"
ROUTERS_FILE = "app/api/routers.py"
REGISTRATIONS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "app/setup/catalog.py": (("MODULES",), ("service.",)),
    ROUTERS_FILE: (("MODULE_ROUTERS",), (V1_IMPORT,)),
}


class Reader:
    def __init__(self) -> None:
        self.files: dict[tuple[Path, Path], list[Path]] = {}
        self.contents: dict[Path, bytes | None] = {}
        self.sources: dict[Path, str | None] = {}

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

    def read(self, path: Path) -> bytes | None:
        if path not in self.contents:
            self.contents[path] = path.read_bytes() if path.is_file() else None
        return self.contents[path]

    def source(self, path: Path) -> str | None:
        if path not in self.sources:
            content = self.read(path)
            try:
                self.sources[path] = content.decode("utf-8") if content is not None else None
            except UnicodeDecodeError:
                self.sources[path] = None
        return self.sources[path]


def _targets_of(node: ast.stmt) -> list[ast.expr]:
    if isinstance(node, ast.Assign):
        return list(node.targets)
    if isinstance(node, ast.AnnAssign):
        return [node.target]
    return []


def _is_registration(node: ast.stmt, names: tuple[str, ...]) -> bool:
    return any(isinstance(item, ast.Name) and item.id in names for item in _targets_of(node))


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


def registration_entry(
    reader: Reader, path: Path, names: tuple[str, ...], prefixes: tuple[str, ...]
) -> bytes:
    source = reader.source(path)
    if source is not None:
        rest = _registration_rest(source, names, prefixes)
        if rest is not None:
            return rest.encode("utf-8")
    return reader.read(path) or b"<missing>"


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


def module_api_files(project: Path) -> dict[str, list[Path]] | None:
    reader = Reader()
    stems = route_ownership(reader.source(project / "server" / ROUTERS_FILE))
    if stems is None:
        return None
    folder = project / "server" / V1_FOLDER
    return {name: [folder / f"{stem}.py" for stem in names] for name, names in stems.items()}
