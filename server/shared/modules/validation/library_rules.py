import ast
from pathlib import Path

from shared.errors.framework import DeclarationError
from shared.modules.libraries import LibrarySpec, library_closure, library_links, library_specs
from shared.modules.validation.pure import check_pure
from shared.modules.validation.report import Problem


def check_libraries(root: Path) -> list[Problem]:
    problems = []
    try:
        specs = library_specs(root)
        links = library_links(root)
        names = {spec.name for spec in specs}
        for spec in specs:
            library_closure(spec.name, links, names)
            problems += check_library_folder(root, spec)
    except (DeclarationError, ValueError, KeyError, TypeError) as error:
        problems.append(Problem("library", 0, "library_declaration", str(error)))
    return problems


def check_library_folder(root: Path, spec: LibrarySpec) -> list[Problem]:
    folder = root / "library" / spec.name
    problems = []
    for required in ("README.md", "public.py", "module.json"):
        if not (folder / required).is_file():
            problems.append(
                Problem(f"library/{spec.name}/{required}", 0, "library_layout", "缺少工具文件")
            )
    problems += export_problems(folder, spec)
    for path in folder.rglob("*"):
        parts = path.relative_to(folder).parts
        if "__pycache__" in parts:
            continue
        allowed = (
            len(parts) == 1
            and parts[0] in {"README.md", "public.py", "module.json", "data.py", "calc"}
        ) or (len(parts) == 2 and parts[0] == "calc" and path.suffix in {".py", ".md"})
        if path.is_symlink() or not allowed:
            problems.append(
                Problem(
                    f"library/{spec.name}/{'/'.join(parts)}",
                    0,
                    "library_layout",
                    "工具文件位置不符合结构",
                )
            )
        if path.is_file() and path.suffix == ".py":
            problems += check_pure(path, root)
    return problems


def export_problems(folder: Path, spec: LibrarySpec) -> list[Problem]:
    public = folder / "public.py"
    if not public.is_file():
        return []
    try:
        tree = ast.parse(public.read_text())
    except SyntaxError as error:
        return [Problem(str(public), error.lineno or 0, "library_exports", "公开入口无法解析")]
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
        ):
            literal = node.value
            if not isinstance(literal, (ast.Tuple, ast.List)):
                return [Problem(str(public), 0, "library_exports", "公开入口的__all__必须是字面量")]
            actual = {
                item.value
                for item in literal.elts
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            }
            break
    else:
        return [Problem(str(public), 0, "library_exports", "公开入口缺少__all__")]
    missing = sorted(set(spec.exports) - actual)
    extra = sorted(actual - set(spec.exports))
    bound = public_bindings(tree)
    undefined = sorted(actual - bound)
    details = [
        f"声明未公开：{names}" if first else f"公开未声明：{names}"
        for first, names in ((True, missing), (False, extra))
        if names
    ]
    if undefined:
        details.append(f"导出名称未定义：{undefined}")
    if not details:
        return []
    return [Problem(str(public), 0, "library_exports", "导出与声明不一致；" + "；".join(details))]


def public_bindings(tree: ast.Module) -> set[str]:
    found = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            found.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            found.update(target.id for target in targets if isinstance(target, ast.Name))
    return found
