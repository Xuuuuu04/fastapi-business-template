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
        raise SystemExit("以下代码发生变化，需要核对状态模型是否仍符合实现：" + "、".join(changed))
    count, failure = explore(fenced=True)
    if failure:
        raise SystemExit("发现违反任务提交规则的执行顺序：" + " → ".join(failure))
    _, mutation = explore(fenced=False)
    if not mutation:
        raise SystemExit("检查器未能发现错误模型中的问题：该模型移除了执行次数编号校验")
    print(
        f"限定范围内的状态检查通过：{count} 个状态；2 个 worker、1 个可重试任务、最多执行 2 次",
        flush=True,
    )
    print("错误模型中会出错的执行顺序：" + " → ".join(mutation), flush=True)
    print(
        "继续检查任务占用有效期结束后，旧执行的数据库写入是否回滚；本项不检查外部操作和资源占用有效期。",
        flush=True,
    )
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
