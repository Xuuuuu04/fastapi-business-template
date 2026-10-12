"""检查清单索引可以重建；只缓存文件身份与派生清单，不替代原始检查证据。"""

import json
import sqlite3
from pathlib import Path
from typing import Any

from fastapi_project.development.check_import import import_legacy
from fastapi_project.development.check_storage import load_cases


# 文件替换、内容修改与utime都使索引失效，mtime不是唯一判断依据。
def file_stamp(path: Path) -> str:
    value = path.stat()
    return f"{value.st_ino}:{value.st_size}:{value.st_mtime_ns}:{value.st_ctime_ns}"


# 清单格式有界；大于4MiB的旧格式必须使用流式转换。
def read_manifest(path: Path) -> tuple[dict[str, Any], Path]:
    root = path.parent
    if path.stat().st_size <= 4 * 1024 * 1024:
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("schema_version") == 2:
            return record, root
    root = root / "_legacy" / path.stem
    return import_legacy(path, root), root


# 只查询或导入实际发生变化的文件；SQLite事务处理同时完成的多份检查。
def indexed(path: Path, connection: sqlite3.Connection) -> tuple[dict[str, Any], Path]:
    stamp = file_stamp(path)
    previous = connection.execute(
        "SELECT stamp, manifest, root FROM check_files WHERE path=?", (str(path),)
    ).fetchone()
    if previous and previous[0] == stamp and Path(previous[2]).is_dir():
        return json.loads(previous[1]), Path(previous[2])
    record, root = read_manifest(path)
    connection.execute(
        "INSERT OR REPLACE INTO check_files VALUES (?, ?, ?, ?)",
        (str(path), stamp, json.dumps(record, ensure_ascii=False), str(root)),
    )
    return record, root


# 索引失效或损坏时重建派生数据库，不删除检查清单或轨迹。
def open_index(folder: Path) -> sqlite3.Connection:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "_index.sqlite3"
    for attempt in range(2):
        connection = sqlite3.connect(path, timeout=60)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS check_files "
                "(path TEXT PRIMARY KEY, stamp TEXT, manifest TEXT, root TEXT)"
            )
            return connection
        except sqlite3.DatabaseError:
            connection.close()
            if attempt:
                raise
            path.unlink(missing_ok=True)
    raise ValueError("检查索引无法建立")


# 同一轮跨工作树或CI导入不能重复计数，也不能用同编号的不同事实互相覆盖。
def read_records(
    project: Path, extra: list[Path] | None, include_cases: bool
) -> list[dict[str, Any]]:
    folder = project / "server/var/development/checks"
    files = {path.resolve() for path in folder.glob("*.json")}
    for directory in extra or []:
        if not directory.is_dir():
            raise ValueError(f"检查记录目录不存在：{directory}")
        files.update(path.resolve() for path in directory.glob("*.json"))
    result: dict[str, dict[str, Any]] = {}
    connection = open_index(folder)
    try:
        connection.execute("BEGIN IMMEDIATE")
        for path in sorted(files):
            record, root = indexed(path, connection)
            identity = record.get("id") or path.name
            if identity in result:
                compare_records(result[identity], record)
                continue
            result[identity] = attach_root(record, root, include_cases)
        connection.commit()
    finally:
        connection.close()
    return sorted(result.values(), key=lambda item: item["finished_at"])


# 绝对位置只用于当前读取，不写进可导出的清单。
def attach_root(record: dict[str, Any], root: Path, include_cases: bool) -> dict[str, Any]:
    for suite in record.get("suites", []):
        suite["_artifact_root"] = str(root)
        if include_cases:
            suite["cases"] = load_cases(suite)
    return record


# 比较独立清单事实；位置及加载结果不是检查内容。
def compare_records(first: dict[str, Any], second: dict[str, Any]) -> None:
    def normalized(record: dict[str, Any]) -> dict[str, Any]:
        return {
            **record,
            "suites": [
                {
                    key: value
                    for key, value in suite.items()
                    if key not in {"_artifact_root", "_cases_loaded", "cases", "case_file"}
                }
                for suite in record.get("suites", [])
            ],
        }

    if normalized(first) != normalized(second):
        raise ValueError("同一轮检查内容不一致")
