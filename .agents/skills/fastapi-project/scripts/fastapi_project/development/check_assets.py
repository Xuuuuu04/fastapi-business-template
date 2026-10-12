"""
检查轨迹按内容摘要压缩保存；摘要不展开SQL明细，按编号查看时校验内容。
"""

import gzip
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

MAX_DETAIL_BYTES = 8 * 1024 * 1024
RUN_FIELDS = (
    "id",
    "root_id",
    "parent_id",
    "parent_step",
    "operation",
    "status",
    "code_version",
    "source_version",
    "started_at",
    "elapsed_ms",
    "gaps",
    "planned",
    "query_budget",
    "import_report",
    "segment",
    "writes",
)
STEP_FIELDS = (
    "name",
    "title",
    "status",
    "source",
    "elapsed_ms",
    "reads",
    "writes",
    "outputs",
    "condition",
    "condition_result",
    "condition_name",
    "condition_source",
    "condition_elapsed_ms",
    "database_count",
    "database_complete",
    "calcs",
)


# 临时文件与目标在同一目录，替换前不会暴露半份检查结果。
def atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=".writing-")
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


# 引用只接受本检查目录内的普通文件，不跟随链接。
def asset_path(root: Path, relative: str) -> Path:
    path = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("检查证据路径越出记录目录")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("检查证据路径越出记录目录")
    current = path
    while current != root:
        if current.is_symlink():
            raise ValueError("检查证据不能使用文件链接")
        current = current.parent
    return path


# 每次运行保留轻量步骤与实际状态；完整轨迹只保存一份压缩对象。
def compact_run(run: dict[str, Any], root: Path) -> dict[str, Any]:
    result = {key: run[key] for key in RUN_FIELDS if key in run}
    result["steps"] = [
        {key: step[key] for key in STEP_FIELDS if key in step} for step in run.get("steps", [])
    ]
    raw = json.dumps(run, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    if len(raw) > MAX_DETAIL_BYTES:
        result["detail_state"] = "truncated"
        result["detail_bytes"] = len(raw)
        return result
    digest = hashlib.sha256(raw).hexdigest()
    relative = f"_runs/{digest}.json.gz"
    path = asset_path(root, relative)
    if not path.exists():
        atomic_bytes(path, gzip.compress(raw, mtime=0))
    result["detail_ref"] = {"file": relative, "sha256": digest, "bytes": len(raw)}
    return result


# 测试结果不重复嵌入完整轨迹；保留通过、失败、跳过与确认样例的独立证据。
def compact_case(case: dict[str, Any], root: Path) -> dict[str, Any]:
    return {
        **{key: value for key, value in case.items() if key != "runs"},
        "runs": [compact_run(run, root) for run in case.get("runs", [])],
    }


# 按需读取有界轨迹；缺失、损坏和摘要不一致都明确失败，不返回伪造的空成功。
def expand_run(run: dict[str, Any]) -> dict[str, Any]:
    reference = run.get("detail_ref")
    if not reference:
        return run
    root = Path(run["_artifact_root"])
    path = asset_path(root, reference["file"])
    try:
        with gzip.open(path, "rb") as source:
            raw = source.read(MAX_DETAIL_BYTES + 1)
    except (OSError, EOFError) as error:
        raise ValueError(f"检查轨迹缺失或损坏：{path.name}") from error
    if len(raw) > MAX_DETAIL_BYTES or hashlib.sha256(raw).hexdigest() != reference["sha256"]:
        raise ValueError(f"检查轨迹内容摘要不一致：{path.name}")
    return json.loads(raw)
