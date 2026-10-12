"""
模块清单由包自己的结构声明生成，名称排序稳定；生成器不继续手工拼接旧登记片段。
"""

import json
from pathlib import Path


# 只从明确的包描述取得名称，业务实现不在生成登记时执行。
def registry_text(root: Path) -> str:
    names = []
    for marker in sorted((root / "service").glob("*/module.json")):
        content = json.loads(marker.read_text())
        name = marker.parent.name
        if content.get("module") != name or marker.is_symlink():
            raise ValueError(f"业务包 {name} 的结构声明无效")
        names.append(name)
    imports = "".join(f"from service.{name}.module import module as {name}\n" for name in names)
    entries = "".join(f"    {name},\n" for name in names)
    return (
        '"""\n模块清单由业务包声明生成，新增与删除后重新生成。\n"""\n\n'
        + imports
        + "from shared.modules.module import Module\n\n"
        + f"MODULES: list[Module] = [\n{entries}]\n"
    )


# 登记是派生代码，命令重复执行不会产生新顺序或重复项。
def write_registry(root: Path) -> Path:
    target = root / "app/setup/catalog.py"
    target.write_text(registry_text(root))
    return target
