"""
历史JSON检查流式转换，转换文件只作派生缓存，原记录与完整轨迹保持可查。
"""

import gzip
import hashlib
import json
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import ijson  # type: ignore[import-untyped]
from fastapi_project.development.check_assets import atomic_bytes, compact_case
from ijson.common import ObjectBuilder  # type: ignore[import-untyped]


# 一次只在内存保留一项测试；不把整个历史JSON或完整数据库轮次载入内存。
def import_legacy(path: Path, root: Path) -> dict[str, Any]:
    identity = hashlib.sha256(str(path.resolve()).encode()).hexdigest()
    meta = ObjectBuilder()
    case: ObjectBuilder | None = None
    number = -1
    output: Any = None
    counts: list[dict[str, int]] = []
    digests: list[Any] = []
    root.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("rb") as source, ExitStack() as stack:
            for prefix, event, value in ijson.parse(source, use_float=True):
                if prefix == "suites.item" and event == "start_map":
                    number += 1
                    counts.append({})
                    digests.append(hashlib.sha256())
                if prefix == "suites.item.cases" and event == "start_array":
                    target = root / f"_cases/{identity}-{number}.jsonl.gz"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    output = stack.enter_context(gzip.open(target, "wt", encoding="utf-8"))
                if prefix.startswith("suites.item.cases.item"):
                    case = consume_result(
                        case, prefix, event, value, root, output, counts[number], digests[number]
                    )
                    continue
                if prefix == "suites.item.cases" and event == "end_array" and output:
                    output.close()
                    output = None
                meta.event(event, value)
    finally:
        if output:
            output.close()
    return imported_manifest(meta.value, root, identity, counts, digests)


# 解析完成的一项立即写出，不在外层事件循环继续嵌套处理。
def consume_result(
    builder: ObjectBuilder | None,
    prefix: str,
    event: str,
    value: Any,
    root: Path,
    output: Any,
    counts: dict[str, int],
    digest: Any,
) -> ObjectBuilder | None:
    builder, completed = consume_case(builder, prefix, event, value)
    if completed is not None:
        write_case(completed, root, output, counts, digest)
    return builder


# ObjectBuilder只处理当前case子树，结束后立即释放它。
def consume_case(
    builder: ObjectBuilder | None, prefix: str, event: str, value: Any
) -> tuple[ObjectBuilder | None, dict[str, Any] | None]:
    builder = builder or ObjectBuilder()
    builder.event(event, value)
    if prefix == "suites.item.cases.item" and event == "end_map":
        return None, builder.value
    return builder, None


# 实际测试状态与轻量轨迹写进有界结果流。
def write_case(
    case: dict[str, Any], root: Path, output: Any, counts: dict[str, int], digest: Any
) -> None:
    outcome = case.get("outcome", "unrecorded")
    counts[outcome] = counts.get(outcome, 0) + 1
    line = json.dumps(compact_case(case, root), ensure_ascii=False, sort_keys=True) + "\n"
    digest.update(line.encode())
    output.write(line)


# 历史格式保留原编号与事实，新派生清单可以删除后重新生成。
def imported_manifest(
    record: dict[str, Any],
    root: Path,
    identity: str,
    counts: list[dict[str, int]],
    digests: list[Any],
) -> dict[str, Any]:
    if record.get("schema_version") != 1:
        raise ValueError("历史检查记录格式不支持")
    for number, suite in enumerate(record.get("suites", [])):
        suite.update(
            case_file=f"_cases/{identity}-{number}.jsonl.gz",
            counts=counts[number],
            case_sha256=digests[number].hexdigest(),
        )
    record["schema_version"] = 2
    record["imported_schema"] = 1
    atomic_bytes(root / f"{identity}.json", json.dumps(record, ensure_ascii=False).encode())
    return record
