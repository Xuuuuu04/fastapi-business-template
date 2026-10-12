"""
证据保留方案保护明确引用、失败历史和同版本最近三轮；所有原件校验后才允许清理。
"""

import hashlib
import json
import os
import re
import shutil
import uuid
from pathlib import Path

from fastapi_project.development.check_assets import asset_path, atomic_bytes, expand_run
from fastapi_project.development.check_index import read_manifest
from fastapi_project.development.check_storage import iter_cases
from fastapi_project.development.evidence_lock import evidence_lock

IDENTITY = re.compile(r"(?<![a-f0-9])[a-f0-9]{32}(?![a-f0-9])")


# 编号只指向当前产品的清单，不接受路径或跨项目定位。
def manifest_path(root: Path, identity: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", identity):
        raise ValueError("检查编号不合法")
    return asset_path(root, identity + ".json")


# 显式固定的理由保存在本机，不能修改检查自身的结果或指纹。
def pin(project: Path, identity: str, reason: str, *, remove: bool = False) -> dict:
    root = asset_path(project, "server/var/development/checks")
    with evidence_lock(root):
        if not manifest_path(root, identity).is_file():
            raise ValueError("当前产品没有该检查原件")
        path = asset_path(root, "_pins/retained.json")
        pins = json.loads(path.read_text()) if path.exists() else {}
        if remove:
            pins.pop(identity, None)
        elif reason.strip():
            pins[identity] = reason.strip()
        else:
            raise ValueError("固定检查需要写明保留理由")
        atomic_bytes(path, (json.dumps(pins, ensure_ascii=False, sort_keys=True) + "\n").encode())
        return pins


# 任务、审查、交付与文档的实际编号引用都保护原件，不根据完成状态丢弃引用。
def references(project: Path) -> tuple[set[str], dict[str, str]]:
    files = [project / "AGENTS.md", project / "README.md"]
    for folder in (project / "doc", project / ".agents/records"):
        asset_path(project, folder.relative_to(project).as_posix())
        for directory, names, items in os.walk(folder):
            names[:] = [
                name for name in names if name not in {"integrations", "evidence-gc", "sources"}
            ]
            files.extend(Path(directory) / item for item in items)
    found: set[str] = set()
    stamps = {}
    for path in sorted(files):
        relative = path.relative_to(project).as_posix()
        if path.suffix not in {".md", ".json"} or not path.is_file():
            continue
        if "/evidence-gc/" in relative or "/integrations/" in relative:
            continue
        asset_path(project, relative)
        raw = path.read_bytes()
        stamps[relative] = hashlib.sha256(raw).hexdigest()
        found.update(IDENTITY.findall(raw.decode()))
    return found, stamps


# 完整校验结果流和轨迹，损坏原件不能通过清理消失，也不能假装还有完整证据。
def assets(root: Path, record: dict) -> set[str]:
    result = set()
    for suite in record.get("suites", []):
        suite = suite | {"_artifact_root": str(root)}
        if "case_file" in suite:
            result.add(suite["case_file"])
        for case in iter_cases(suite):
            for run in case.get("runs", []):
                if run.get("detail_ref"):
                    expand_run(run)
                    result.add(run["detail_ref"]["file"])
    return result


# 每组源码、范围保留最近三轮，所有失败和旧格式也保留，不能删成稳定绿色。
def preserved(records: list[dict], explicit: set[str]) -> set[str]:
    result = set(explicit)
    groups: dict[str, list[str]] = {}
    for record in sorted(records, key=lambda item: item["finished_at"], reverse=True):
        identity = record["id"]
        if not record.get("passed") or record.get("schema_version") != 2:
            result.add(identity)
        key = json.dumps([record.get("fingerprints"), record.get("scope")], sort_keys=True)
        group = groups.setdefault(key, [])
        if len(group) < 3:
            result.add(identity)
            group.append(identity)
    return result


# 只扫描当前检查目录的清单和资产，旧转换缓存保持原样，不扩大删除范围。
def snapshot(root: Path) -> dict[str, str]:
    paths = list(root.glob("*.json"))
    pin_path = root / "_pins/retained.json"
    if pin_path.exists():
        paths.append(pin_path)
    for name in ("_cases", "_runs"):
        paths.extend((root / name).rglob("*"))
    result = {}
    for path in sorted(paths):
        name = path.relative_to(root).as_posix()
        checked = asset_path(root, name)
        if checked.is_file():
            result[name] = hashlib.sha256(checked.read_bytes()).hexdigest()
    return result


# 导入的自定义文件名及旧清单永久保留，实际引用按各自资产根目录核对。
def record_inventory(root: Path, stamps: dict[str, str]) -> tuple[dict, dict, set[str]]:
    records: dict[str, dict] = {}
    owned: dict[str, set[str]] = {}
    protected: set[str] = set()
    for name in stamps:
        if "/" in name:
            continue
        record, folder = read_manifest(asset_path(root, name))
        identity = record.get("id") or Path(name).stem
        if not isinstance(identity, str) or not identity:
            raise ValueError("检查清单缺少有效编号")
        record = record | {"id": identity}
        if identity in records and records[identity] != record:
            raise ValueError("同一编号的检查原件存在不同内容")
        records[identity] = record
        prefix = folder.relative_to(root)
        owned.setdefault(identity, set()).update(
            (prefix / relative).as_posix() for relative in assets(folder, record)
        )
        if name != identity + ".json" or record.get("imported_schema") == 1:
            protected.add(identity)
    return records, owned, protected


# 在同一发布锁中计算待删清单及共享对象，计划摘要包含引用和全部原件内容。
def retention_plan(project: Path) -> dict:
    root = asset_path(project, "server/var/development/checks")
    stamps = snapshot(root)
    explicit, reference_stamps = references(project)
    pin_path = asset_path(root, "_pins/retained.json")
    explicit.update(json.loads(pin_path.read_text()) if pin_path.exists() else {})
    records, owned, protected = record_inventory(root, stamps)
    keep = preserved(list(records.values()), explicit | protected)
    used = set().union(*(owned[identity] for identity in owned if identity in keep))
    delete = sorted(
        [identity + ".json" for identity in owned if identity not in keep]
        + [name for name in stamps if name.startswith(("_cases/", "_runs/")) and name not in used]
    )
    digest = hashlib.sha256(
        json.dumps([stamps, reference_stamps, delete], sort_keys=True).encode()
    ).hexdigest()
    return {"preview_id": digest, "delete": delete, "keep": sorted(keep & owned.keys())}


# 默认只给预览；应用必须带相同摘要并重新核对，普通失败把已移动的全部原件恢复。
def collect(project: Path, expected: str | None = None) -> dict:
    root = asset_path(project, "server/var/development/checks")
    with evidence_lock(root):
        plan = retention_plan(project)
        if expected is None:
            return plan | {"applied": False}
        if expected != plan["preview_id"]:
            raise ValueError("证据或引用在预览后变化，请重新预览")
        archive = asset_path(project, ".agents/records/evidence-gc/" + uuid.uuid4().hex)
        moved = []
        try:
            for name in plan["delete"]:
                target = archive / name
                target.parent.mkdir(parents=True, exist_ok=True)
                asset_path(root, name).replace(target)
                moved.append(name)
        except OSError:
            for name in reversed(moved):
                (archive / name).replace(asset_path(root, name))
            raise
        # 清理后留下隔离目录不会影响有效原件；目录仍存在时可人工回收磁盘空间。
        if archive.exists():
            shutil.rmtree(archive, ignore_errors=True)
        return plan | {"applied": True}
