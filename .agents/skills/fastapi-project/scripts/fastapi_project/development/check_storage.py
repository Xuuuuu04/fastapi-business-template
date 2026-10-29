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
from fastapi_project.development.evidence_lock import evidence_lock


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


def save_record(project: Path, record: dict[str, Any]) -> Path:
    root = project / "server/var/development/checks"
    with evidence_lock(root):
        return publish_record(root, record)


def publish_record(root: Path, record: dict[str, Any]) -> Path:
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


def load_cases(suite: dict[str, Any]) -> list[dict[str, Any]]:
    if "case_file" in suite and not suite.get("_cases_loaded"):
        suite["cases"] = list(iter_cases(suite))
        suite["_cases_loaded"] = True
    return suite.get("cases", [])


def export_record(source: Path, destination: Path) -> Path:
    from contextlib import ExitStack

    with ExitStack() as stack:
        roots = {root.resolve(): root for root in (source.parent, destination)}
        for _, root in sorted(roots.items()):
            stack.enter_context(evidence_lock(root))
        return publish_export(source, destination)


def publish_export(source: Path, destination: Path) -> Path:
    source = asset_path(source.parent, source.name)
    record = json.loads(source.read_text())
    destination.mkdir(parents=True, exist_ok=True)
    if record.get("schema_version") == 2:
        for suite in record.get("suites", []):
            suite["_artifact_root"] = str(source.parent)
            for case in iter_cases(suite):
                copy_case_assets(source.parent, destination, case)
            copy_asset(source.parent, destination, suite["case_file"])
            suite.pop("_artifact_root", None)
    target = asset_path(destination, source.name)
    atomic_bytes(target, (json.dumps(record, ensure_ascii=False) + "\n").encode())
    return target


def copy_case_assets(source: Path, destination: Path, case: dict[str, Any]) -> None:
    for run in case.get("runs", []):
        if run.get("detail_ref"):
            expand_run(run)
            copy_asset(source, destination, run["detail_ref"]["file"])


def copy_asset(source: Path, destination: Path, relative: str) -> None:
    target = asset_path(destination, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(asset_path(source, relative), target)
