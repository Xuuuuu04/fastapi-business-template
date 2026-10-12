"""CheckRecord v2：检查清单、测试结果流和运行对象分别保存，读取范围由调用方选择。"""

import gzip
import hashlib
import json
import shutil
import tempfile
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi_project.development.check_assets import (
    asset_path,
    atomic_bytes,
    compact_case,
    expand_run,
)


# 用唯一临时流保存各项结果，最终清单写入前所有引用已经就绪。
def write_cases(root: Path, identity: str, number: int, cases: Any) -> dict[str, Any]:
    relative = f"_cases/{identity}-{number}.jsonl.gz"
    target = asset_path(root, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    digest = hashlib.sha256()
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temporary:
        name = Path(temporary.name)
    try:
        with gzip.open(name, "wt", encoding="utf-8") as output:
            for case in cases:
                outcome = case.get("outcome", "unrecorded")
                counts[outcome] = counts.get(outcome, 0) + 1
                line = json.dumps(compact_case(case, root), ensure_ascii=False, sort_keys=True)
                digest.update((line + "\n").encode())
                output.write(line + "\n")
        name.replace(target)
    finally:
        name.unlink(missing_ok=True)
    return {"cases": [], "case_file": relative, "case_sha256": digest.hexdigest(), "counts": counts}


# 一轮检查的实际范围与数据库分别保存，源文件变化状态不能被统计数量覆盖。
def save_record(project: Path, record: dict[str, Any]) -> Path:
    root = project / "server/var/development/checks"
    root.mkdir(parents=True, exist_ok=True)
    identity = uuid.uuid4().hex
    suites = [
        {
            **{key: value for key, value in suite.items() if key != "cases"},
            **write_cases(root, identity, number, suite.get("cases", [])),
        }
        for number, suite in enumerate(record.get("suites", []))
    ]
    manifest = {
        **record,
        "schema_version": 2,
        "id": identity,
        "finished_at": datetime.now(UTC).isoformat(),
        "suites": suites,
    }
    path = root / f"{identity}.json"
    atomic_bytes(path, (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode())
    return path


# 项目摘要只加载选中轮次的轻量结果，旧内存记录仍可直接使用。
def iter_cases(suite: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if suite.get("_cases_loaded"):
        yield from suite["cases"]
        return
    relative = suite.get("case_file")
    if not relative:
        yield from suite.get("cases", [])
        return
    root = Path(suite["_artifact_root"])
    path = asset_path(root, relative)
    try:
        digest = hashlib.sha256()
        with gzip.open(path, "rt", encoding="utf-8") as source:
            for line in source:
                digest.update(line.encode())
                case = json.loads(line)
                for run in case.get("runs", []):
                    run["_artifact_root"] = str(root)
                yield case
        if suite.get("case_sha256") and digest.hexdigest() != suite["case_sha256"]:
            raise ValueError("测试结果流摘要不一致")
    except (OSError, EOFError, ValueError) as error:
        raise ValueError(f"测试证据缺失或损坏：{path.name}") from error


# 仅在需要模块或具体测试结果时展开，不在全历史上载入运行轨迹。
def load_cases(suite: dict[str, Any]) -> list[dict[str, Any]]:
    if "case_file" in suite and not suite.get("_cases_loaded"):
        suite["cases"] = list(iter_cases(suite))
        suite["_cases_loaded"] = True
    return suite.get("cases", [])


# 导出完整检查包，清单最后写入；只复制JSON会明确缺证据，不猜别的目录。
def export_record(source: Path, destination: Path) -> Path:
    record = json.loads(source.read_text())
    destination.mkdir(parents=True, exist_ok=True)
    if record.get("schema_version") == 2:
        for suite in record.get("suites", []):
            suite["_artifact_root"] = str(source.parent)
            for case in iter_cases(suite):
                for run in case.get("runs", []):
                    if run.get("detail_ref"):
                        expand_run(run)
                        copy_asset(source.parent, destination, run["detail_ref"]["file"])
            copy_asset(source.parent, destination, suite["case_file"])
            suite.pop("_artifact_root", None)
    target = asset_path(destination, source.name)
    atomic_bytes(target, (json.dumps(record, ensure_ascii=False) + "\n").encode())
    return target


# 复制范围由清单明确给出，文件链接与越界路径统一拒绝。
def copy_asset(source: Path, destination: Path, relative: str) -> None:
    target = asset_path(destination, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(asset_path(source, relative), target)
