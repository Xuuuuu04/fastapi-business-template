import json
from pathlib import Path


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
        imports
        + "from shared.modules.module import Module\n\n"
        + f"MODULES: list[Module] = [\n{entries}]\n"
    )


def write_registry(root: Path) -> Path:
    target = root / "app/setup/catalog.py"
    target.write_text(registry_text(root))
    return target
