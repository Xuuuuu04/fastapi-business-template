"""
业务别名直接附着在已登记模块和操作上，无独立引用表。
"""

from collections.abc import Sequence

from shared.modules.module import Module


# 模块别名全局唯一，操作别名在模块内唯一；大小写和首尾空白统一比较。
def check_aliases(modules: Sequence[Module]) -> list[str]:
    problems = check_scope([(m.name, m.aliases) for m in modules])
    for module in modules:
        problems += check_scope([(c.name, c.aliases) for c in module.provides])
    return problems


# 名称也参与冲突检查，拒绝空别名和非字符串；别名不改变调用名称。
def check_scope(items: list[tuple[str, tuple[str, ...]]]) -> list[str]:
    owners = {name.casefold(): name for name, _ in items}
    problems = []
    for name, aliases in items:
        if not isinstance(aliases, tuple):
            problems.append(f"{name} 的 aliases 必须是字符串元组")
            continue
        for alias in aliases:
            if not isinstance(alias, str) or not alias.strip():
                problems.append(f"{name} 有空或非字符串别名")
                continue
            key = alias.strip().casefold()
            if key in owners:
                problems.append(f"别名 {alias} 冲突：{owners[key]} / {name}")
            else:
                owners[key] = name
    return problems
