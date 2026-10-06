"""
继续读取的命令保留外部检查目录；只处理工具生成的入口，不改实际运行证据。
"""

import copy
import shlex
from collections.abc import Iterator
from pathlib import Path
from typing import Any


# 有 next 的模块是工具的摘要投影；完整模块内的原始测试对象不进入命令改写。
def module_links(module: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if "next" not in module:
        return
    yield module
    yield from (item for item in module.get("operations", []) if "next" in item)
    for suite in module["tests"]["latest"].values():
        yield from suite["problems"]


# 只遍历本工具生成的 next 字段，不进入测试参数、步骤产出或原始运行对象。
def generated_links(result: dict[str, Any]) -> Iterator[dict[str, Any]]:
    modules = list(result.get("modules", {}).values())
    if "tests" in result:
        modules.append(result)
    for module in modules:
        yield from module_links(module)
    for name in ("latest_check", "latest_full_check"):
        check = result.get(name)
        if check is not None:
            for suite in check["suites"].values():
                yield from suite["problems"]
    if "checks" in result:
        for suite in result["checks"]["latest"].values():
            yield from suite["problems"]
    if result.get("view") == "summary":
        for line in result.get("lines", []):
            yield from line["packages"]


# 目录通过 shlex 作为参数引用，含空格的路径仍可原样使用；不修改共享的状态对象。
def with_check_directories(result: dict[str, Any], directories: list[Path]) -> dict[str, Any]:
    if not directories:
        return result
    projected = copy.deepcopy(result)
    arguments = [argument for path in directories for argument in ("--checks", str(path.resolve()))]
    suffix = shlex.join(arguments)
    for entry in generated_links(projected):
        entry["next"] = f"{entry['next']} {suffix}"
    return projected
