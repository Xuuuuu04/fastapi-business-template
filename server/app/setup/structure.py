"""
默认服务与 worker 在创建资源前检查业务包、计算步骤、依赖方向和框架文件摘要。
开发包越界时拒绝启动；测试显式提供的临时模块不检查磁盘目录。
"""

from collections.abc import Sequence
from pathlib import Path

from shared.errors.framework import ConfigError
from shared.flow.step import Condition, Step
from shared.modules.layout import check_layout
from shared.modules.module import Module
from tools.framework_lock import differences
from tools.quality.imports import check_imports

ROOT = Path(__file__).resolve().parents[2]


# 框架更新必须先检查真实差异并更新摘要，不能带着无意改动启动。
def check_structure(modules: Sequence[Module], root: Path = ROOT) -> None:
    problems = check_layout(root, (module.name for module in modules))
    problems += step_locations(modules)
    problems += [problem.text() for problem in check_imports(root)]
    changes = differences(root)
    if changes:
        problems += ["框架文件与已确认的摘要不一致：" + change for change in changes]
    if problems:
        raise ConfigError(problems)


# 每个计算节点必须来自对应模块的 steps/，条件也使用相同位置规则。
def step_locations(modules: Sequence[Module]) -> list[str]:
    problems = []
    for module in modules:
        prefix = f"service.{module.name}.steps."
        parts = (part for flow in module.provides.values() for part in flow.steps)
        for part in parts:
            nodes: list[Step | Condition] = [part]
            if part.when:
                nodes.append(part.when)
            for node in nodes:
                if not node.func.__module__.startswith(prefix):
                    problems.append(
                        f"{node.source}：计算节点 {node.name} "
                        f"必须写在 service/{module.name}/steps/ 中"
                    )
    return problems
