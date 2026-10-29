import hashlib
import json
from pathlib import Path


def template_tool_file(name: str) -> bool:
    return (name.startswith(".agents/skills/") and "/scripts/" in name) or name.startswith(
        "server/devtools/"
    )


def template_tools_unchanged(root: Path) -> bool:
    path = root / "template-source.json"
    if not path.is_file():
        return False
    try:
        recorded = json.loads(path.read_text(encoding="utf-8")).get("files", {})
        tools = {name: digest for name, digest in recorded.items() if template_tool_file(name)}
        return bool(tools) and all(
            (root / relative).is_file()
            and hashlib.sha256((root / relative).read_bytes()).hexdigest() == digest
            for relative, digest in tools.items()
        )
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def template_tool(path: Path, root: Path) -> bool:
    relative = path.relative_to(root / "server").as_posix()
    if relative.startswith("tests/architecture/"):
        return path.name != "test_structure.py"
    return relative == "tests/framework/test_commands.py"
