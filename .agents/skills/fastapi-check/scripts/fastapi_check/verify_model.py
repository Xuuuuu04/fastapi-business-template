import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from fastapi_check.job_model import explore
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


def main() -> None:
    changed = check_mapping()
    if changed:
        raise SystemExit("状态模型与实现需要重新核对：" + "、".join(changed))
    count, failure = explore(fenced=True)
    if failure:
        raise SystemExit("状态不变量失败：" + " → ".join(failure))
    _, mutation = explore(fenced=False)
    if not mutation:
        raise SystemExit("检查器没有识别移除尝试编号校验的错误模型")
    print(
        f"有界状态检查通过：{count} 个状态；2 个 worker、1 个可重试任务、最多 2 次尝试", flush=True
    )
    print("错误模型反例：" + " → ".join(mutation), flush=True)
    print("继续核对真实实现的过期尝试回滚；不包含外部副作用和资源租约。", flush=True)
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/framework/test_job_commit.py::test_takeover_after_precheck_rolls_back_old_commit",
    ]
    raise SystemExit(subprocess.run(command, cwd=ROOT, check=False).returncode)


if __name__ == "__main__":
    main()
