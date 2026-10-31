from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from fastapi_check.quality.rules import ROOT

from shared.modules.catalog import Catalog
from shared.modules.libraries import library_links
from shared.modules.validation.framework_files import FRAMEWORK, REGISTRATION

MODULE_AREAS = (
    ("server/service/", "代码"),
    ("server/app/api/v1/", "接口"),
    ("server/tests/modules/", "测试"),
    ("server/tests/integration/", "测试"),
)
PRODUCT_FILES = {entry.removeprefix("../") for entry in REGISTRATION if entry.startswith("../")}


@dataclass(frozen=True)
class ImpactScope:
    direct: list[str]
    full_check: bool
    full_check_reasons: list[str]
    unmapped: list[str]


def module_area(path: str, modules: Iterable[str] = ()) -> tuple[str, str] | None:
    for prefix, area in MODULE_AREAS:
        if not path.startswith(prefix):
            continue
        parts = PurePosixPath(path[len(prefix) :]).parts
        if prefix == "server/app/api/v1/":
            if not parts or PurePosixPath(parts[-1]).suffix != ".py":
                return None
            stem = PurePosixPath(parts[0]).stem
            owner = next(
                (
                    name
                    for name in sorted(modules, key=len, reverse=True)
                    if stem == name or stem.startswith(name + "_")
                ),
                None,
            )
            return (owner, area) if owner is not None else None
        if len(parts) > 1:
            if prefix == "server/tests/integration/" and parts[0] == "system":
                return None
            return parts[0], area
    return None


def framework_files(files: Iterable[str]) -> list[str]:
    return sorted(
        path
        for path in files
        if path.startswith(".agents/skills/")
        or (
            path.startswith("server/")
            and any(path[7:] == entry or path[7:].startswith(entry + "/") for entry in FRAMEWORK)
        )
    )


def shared_reason(path: str, framework: set[str], modules: Iterable[str] = ()) -> str:
    if path in framework:
        return f"框架改动：{path}；需检查全部登记模块"
    if path.startswith("server/migrations/"):
        return f"数据库迁移改动：{path}；可能影响共用数据库"
    if path.startswith("server/library/"):
        return f"工具包改动：{path}；检查工具包本身和全部调用方"
    if path.startswith("doc/api/"):
        return f"公共接口描述改动：{path}；无法仅凭路径确定调用方"
    if path.startswith("server/tests/") and module_area(path, modules) is None:
        return f"公共测试改动：{path}；需检查全部登记模块"
    if path.startswith(("server/app/", "server/service/")) and module_area(path, modules) is None:
        return f"未归属模块的公共代码：{path}；保守检查全部登记模块"
    if path == "server/uv.lock":
        return f"项目共用依赖改动：{path}"
    return ""


def code_paths(files: Iterable[str]) -> list[str]:
    return sorted(
        path
        for path in set(files)
        if not any(path == item or path.startswith(item + "/") for item in PRODUCT_FILES)
    )


def impact_scope(files: Iterable[str], catalog: Catalog, root: Path = ROOT) -> ImpactScope:
    paths = code_paths(files)
    registered = sorted(catalog.modules)
    direct: set[str] = set()
    unmapped = []
    tools = library_links(root)
    for path in paths:
        users = tool_impact(path, tools, catalog)
        owner = module_area(path, registered)
        if users:
            direct |= users
        elif owner is None:
            unmapped.append(path)
        else:
            direct.add(owner[0])
    framework = set(framework_files(paths))
    reasons = [reason for path in paths if (reason := shared_reason(path, framework, registered))]
    reasons += [
        f"模块 {name} 未登记；无法确定完整调用方，需先登记或确认删除"
        for name in sorted(direct - set(registered))
    ]
    return ImpactScope(sorted(direct), bool(reasons), sorted(reasons), unmapped)


def tool_impact(path: str, tools: dict[str, list[str]], catalog: Catalog) -> set[str]:
    if not path.startswith("server/library/"):
        return set()
    parts = PurePosixPath(path).parts
    if len(parts) < 3:
        return set()
    return tool_users(parts[2], tools).intersection(catalog.modules)


def tool_users(name: str, links: dict[str, list[str]]) -> set[str]:
    found = set()
    pending = [name]
    while pending:
        target = pending.pop()
        for user, dependencies in links.items():
            if target in dependencies and user not in found:
                found.add(user)
                pending.append(user)
    return found
