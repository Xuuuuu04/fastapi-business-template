import ast
import hashlib
import json
from pathlib import Path

from fastapi_check.quality.rules import PROJECT, ROOT

MAPPING = PROJECT / ".agents/skills/fastapi-check/assets/job_model.json"


def source_hash(path: Path, symbol: str) -> str:
    code = path.read_text(encoding="utf-8")
    tree = ast.parse(code)
    node: ast.AST = tree
    for name in symbol.split("."):
        node = next(
            child for child in ast.iter_child_nodes(node) if getattr(child, "name", "") == name
        )
    text = ast.get_source_segment(code, node)
    if text is None:
        raise StopIteration(symbol)
    return hashlib.sha256(text.encode()).hexdigest()


def check_mapping() -> list[str]:
    entries = json.loads(MAPPING.read_text(encoding="utf-8"))
    changed = []
    for entry in entries:
        try:
            current = source_hash(ROOT / entry["file"], entry["symbol"])
        except (OSError, SyntaxError, StopIteration):
            current = "missing"
        if current != entry["sha256"]:
            changed.append(f"{entry['file']}:{entry['symbol']}")
    return changed


def require_mapping() -> None:
    changed = check_mapping()
    if changed:
        raise ValueError("以下代码发生变化，需要核对状态模型是否仍符合实现：" + "、".join(changed))
