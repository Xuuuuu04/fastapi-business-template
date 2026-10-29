import shlex
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from fastapi_check.quality.rules import ROOT

from shared.modules.catalog import Catalog
from shared.modules.libraries import library_links
from shared.modules.validation.framework_files import FRAMEWORK

MODULE_AREAS = (
    ("server/service/", "代码"),
    ("doc/", "样例"),
    ("server/app/api/v1/", "接口"),
    ("server/tests/modules/", "测试"),
    ("server/tests/integration/", "测试"),
)
CHECK = "APP_DISABLED_MODULES='[]' uv run dev check"


@dataclass(frozen=True)
class ImpactScope:
    direct: list[str]
    dependents: list[str]
    affected: list[str]
    reasons: dict[str, list[str]]
    commands: list[str]
    full_check: bool
    full_check_reasons: list[str]
    registered: list[str]
    enabled: list[str]
    unknown: list[str]
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
            if (prefix == "doc/" and parts[0] == "api") or (
                prefix == "server/tests/integration/" and parts[0] == "system"
            ):
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
    if path.startswith("doc/api/"):
        return f"公共接口描述改动：{path}；无法仅凭路径确定调用方"
    if path.startswith("server/tests/") and module_area(path, modules) is None:
        return f"公共测试改动：{path}；需检查全部登记模块"
    if path.startswith(("server/app/", "server/service/")) and module_area(path, modules) is None:
        return f"未归属模块的公共代码：{path}；保守检查全部登记模块"
    if path == "server/uv.lock":
        return f"项目共用依赖改动：{path}"
    return ""


def dependent_reasons(catalog: Catalog, direct: Iterable[str]) -> dict[str, list[str]]:
    reverse: dict[str, list[tuple[str, str]]] = {}
    for caller, provider, operation in sorted(set(catalog.edges())):
        reverse.setdefault(provider, []).append((caller, operation))
    pending = deque(sorted(direct))
    seen = set(pending)
    reasons: dict[str, set[str]] = {}
    while pending:
        provider = pending.popleft()
        for caller, operation in reverse.get(provider, []):
            reasons.setdefault(caller, set()).add(
                f"{caller} 调用 {provider}（{operation}）；{provider} 已在影响范围"
            )
            if caller not in seen:
                seen.add(caller)
                pending.append(caller)
    return {name: sorted(items) for name, items in sorted(reasons.items())}


def impact_scope(
    files: Iterable[str],
    catalog: Catalog,
    disabled_modules: Iterable[str] = (),
    root: Path = ROOT,
) -> ImpactScope:
    paths = sorted(set(files))
    registered = sorted(catalog.modules)
    direct_reasons: dict[str, list[str]] = {}
    unmapped = []
    tools = library_links(root)
    for path in paths:
        if record_tool_impact(path, tools, catalog, direct_reasons):
            continue
        owner = module_area(path, registered)
        if owner is None:
            unmapped.append(path)
        else:
            name, area = owner
            direct_reasons.setdefault(name, []).append(f"{area}改动：{path}")
    direct = sorted(direct_reasons)
    unknown = sorted(set(direct) - set(registered))
    framework = set(framework_files(paths))
    full_reasons = [
        reason for path in paths if (reason := shared_reason(path, framework, registered))
    ]
    full_reasons += [
        f"模块 {name} 未登记；无法确定完整调用方，需先登记或确认删除" for name in unknown
    ]
    dependencies = dependent_reasons(catalog, direct)
    dependents = sorted(set(dependencies) - set(direct))
    affected = sorted(set(direct) | set(dependents) | (set(registered) if full_reasons else set()))
    reasons = {
        name: sorted(direct_reasons.get(name, []) + dependencies.get(name, []) + full_reasons)
        for name in affected
    }
    commands = check_commands(affected, bool(full_reasons))
    return ImpactScope(
        direct,
        dependents,
        affected,
        reasons,
        commands,
        bool(full_reasons),
        sorted(full_reasons),
        registered,
        sorted(set(registered) - set(disabled_modules)),
        unknown,
        unmapped,
    )


def record_tool_impact(
    path: str, tools: dict[str, list[str]], catalog: Catalog, reasons: dict[str, list[str]]
) -> bool:
    if not path.startswith("server/library/"):
        return False
    parts = PurePosixPath(path).parts
    if len(parts) < 3:
        return False
    users = tool_users(parts[2], tools).intersection(catalog.modules)
    for user in users:
        reasons.setdefault(user, []).append(f"工具{parts[2]}改动：{path}")
    return bool(users)


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


def check_commands(affected: list[str], full: bool) -> list[str]:
    if full:
        return [CHECK]
    if not affected:
        return []
    return [CHECK + " " + " ".join(f"--module {shlex.quote(name)}" for name in affected)]


def scope_markdown(scope: ImpactScope) -> list[str]:
    lines = [
        "检查范围按完整登记模块计算（含 Step.uses 与 Step.later），不因关闭模块缩小。",
        f"- 完整登记范围：{'、'.join(scope.registered) or '无'}",
        f"- 当前启用范围：{'、'.join(scope.enabled) or '无'}（仅说明运行配置）",
        f"- 直接改动：{'、'.join(scope.direct) or '无'}",
        f"- 直接或传递调用方：{'、'.join(scope.dependents) or '无'}",
        f"- 建议检查：{'、'.join(scope.affected) or '无'}",
        "",
    ]
    for name, reasons in scope.reasons.items():
        lines.append(f"- {name}：{'；'.join(reasons)}")
    if scope.unknown:
        lines += ["", f"未登记模块：{'、'.join(scope.unknown)}；不能确认其下游完整性。"]
    lines += ["", "建议在 server 目录执行（显式启用全部登记模块，尚未执行）："]
    lines += [f"- `{command}`" for command in scope.commands] or ["没有模块检查建议。"]
    lines += ["", "仅使用当前静态声明；删除的调用或未声明的外部调用仍需人工确认。"]
    return lines
