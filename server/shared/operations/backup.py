"""
数据库与文件同次归档，并在新库/新目录恢复校验；从不覆盖源库。
"""

import asyncio
import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

Verify = Callable[[str, Path], Awaitable[None]]


# 选用配置目录中的工具；为空时从 PATH 查找。
def tool_path(tool: str, pg_bin: str = "") -> str:
    return str(Path(pg_bin) / tool) if pg_bin else tool


# 读取工具主版本，如 “pg_restore (PostgreSQL) 17.2” 得到 17；无法运行时报告缺少工具。
async def tool_major(tool: str) -> int:
    try:
        process = await asyncio.create_subprocess_exec(
            tool, "--version", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
    except FileNotFoundError as error:
        name = Path(tool).name
        raise RuntimeError(
            f"找不到{name}，请安装与数据库同版本的PostgreSQL客户端，或配置operations.pg_bin"
        ) from error
    out, _ = await process.communicate()
    found = re.search(rb"(\d+)(?:\.\d+)?", out)
    if process.returncode or not found:
        raise RuntimeError(f"无法读取{Path(tool).name}版本")
    return int(found.group(1))


# 备份与恢复工具主版本必须与数据库相同：
# 新版 pg_restore 会向旧库发出旧库不认识的设置（如 transaction_timeout），恢复必然失败。
async def check_tools(connection: Any, pg_bin: str) -> None:
    server = int(await connection.scalar(text("SHOW server_version_num"))) // 10000
    for tool in ("pg_dump", "pg_restore"):
        major = await tool_major(tool_path(tool, pg_bin))
        if major != server:
            raise RuntimeError(
                f"{tool}主版本{major}与数据库主版本{server}不一致；请安装postgresql-client-{server}，"
                f"或把operations.pg_bin设为该版本工具目录。未生成备份。"
            )


# pg工具密码通过环境传递，不写命令行和报告；错误只报告类型/返回码。
async def command(tool: str, url: str, extra: list[str]) -> None:
    target = make_url(url)
    env = {**os.environ, "PGPASSWORD": target.password or ""}
    args = [
        tool,
        "-h",
        target.host or "localhost",
        "-p",
        str(target.port or 5432),
        "-U",
        target.username or "",
        "-d",
        target.database or "",
        *extra,
    ]
    process = await asyncio.create_subprocess_exec(
        *args, env=env, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
    )
    try:
        async with asyncio.timeout(3600):
            code = await process.wait()
    except BaseException:
        process.kill()
        await process.wait()
        raise
    if code:
        raise RuntimeError(f"{tool}失败（退出码{code}）")


# 数量来自同一数据库快照，使用反射的实际表，不遗漏关闭模块历史表。
async def counts(connection: Any) -> dict[str, int]:
    names = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
    quote = connection.dialect.identifier_preparer.quote
    result = {}
    for name in sorted(names):
        result[name] = int(await connection.scalar(text(f"SELECT count(*) FROM {quote(name)}")))
    return result


# SQLite backup读取一致快照，随后在备份本身计算行数。
def sqlite_snapshot(source: str, target: Path) -> None:
    path = Path(make_url(source).database or "").resolve()
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as src, sqlite3.connect(target) as dst:
        src.backup(dst, pages=256, sleep=0.01)


# PostgreSQL导出快照跨pg_dump与行数统计，完成前保持原事务。
async def snapshot(url: str, folder: Path, pg_bin: str = "") -> dict[str, Any]:
    if make_url(url).get_backend_name() == "sqlite":
        await asyncio.to_thread(sqlite_snapshot, url, folder / "database.db")
        engine = create_async_engine("sqlite+aiosqlite:///" + str(folder / "database.db"))
        try:
            async with engine.connect() as conn:
                return dict(rows=await counts(conn), schema="")
        finally:
            await engine.dispose()
    engine = create_async_engine(url, isolation_level="REPEATABLE READ")
    try:
        async with engine.begin() as conn:
            await check_tools(conn, pg_bin)
            schema = str(await conn.scalar(text("SELECT current_schema()")))
            token = str(await conn.scalar(text("SELECT pg_export_snapshot()")))
            rows = await counts(conn)
            await command(
                tool_path("pg_dump", pg_bin),
                url,
                [
                    "--format=custom",
                    "--no-owner",
                    "--no-acl",
                    "--schema=" + schema,
                    "--snapshot=" + token,
                    "--file=" + str(folder / "database.dump"),
                ],
            )
            return dict(rows=rows, schema=schema)
    finally:
        await engine.dispose()


# 复制本地文件拒绝符号链接；文件与数据库不是跨系统原子快照，报告明确时间范围。
def local_snapshot(source: Path, target: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    if not source.exists():
        return hashes
    for file in source.rglob("*"):
        if file.is_symlink():
            raise ValueError("备份文件区不允许符号链接")
        if not file.is_file():
            continue
        key = file.relative_to(source).as_posix()
        dest = target / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, dest)
        with dest.open("rb") as stream:
            hashes[key] = hashlib.file_digest(stream, "sha256").hexdigest()
    return hashes


# S3对象分块下载到同次归档；不会修改真实对象，版本一致性需对象存储策略保证。
async def files_snapshot(settings: Any, folder: Path) -> dict[str, str]:
    if settings.file_storage == "local":
        return await asyncio.to_thread(local_snapshot, Path(settings.file_root), folder)
    from shared.files.storage import S3Files, S3Options

    storage = S3Files(
        S3Options(
            settings.s3_bucket,
            settings.s3_endpoint,
            settings.s3_region,
            settings.s3_access_key,
            settings.s3_secret_key.get_secret_value() if settings.s3_secret_key else "",
        )
    )
    return await asyncio.to_thread(s3_snapshot, storage, settings.s3_bucket, folder)


# 原对象键检查，流式下载和摘要计算，避免整桶正文进入内存。
def s3_snapshot(storage: Any, bucket: str, folder: Path) -> dict[str, str]:
    from shared.files.storage import check_key

    hashes: dict[str, str] = {}
    client = storage.client
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        for item in page.get("Contents", []):
            key = check_key(item["Key"])
            dest = folder / key
            dest.parent.mkdir(parents=True, exist_ok=True)
            client.download_file(bucket, key, str(dest))
            with dest.open("rb") as stream:
                hashes[key] = hashlib.file_digest(stream, "sha256").hexdigest()
    return hashes


# 创建随机恢复数据库只在已配置源服务器，源数据库名绝不作为删除对象。
async def postgres_restore(
    url: str, folder: Path, verify: Verify, expected: dict[str, Any], pg_bin: str = ""
) -> None:
    name = "fastapi_restore_" + secrets.token_hex(8)
    target = make_url(url).set(database=name)
    admin = create_async_engine(url, isolation_level="AUTOCOMMIT")
    created = False
    try:
        async with admin.connect() as conn:
            await conn.execute(text(f'CREATE DATABASE "{name}"'))
            created = True
        restore = target.render_as_string(hide_password=False)
        await command(
            tool_path("pg_restore", pg_bin),
            restore,
            ["--no-owner", "--no-acl", "--exit-on-error", str(folder / "database.dump")],
        )
        await verify_restore(restore, folder, expected, verify)
    finally:
        if created:
            async with admin.connect() as conn:
                await conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        await admin.dispose()


# 校验实际行数、文件摘要及启动ready；迁移版本由ready校验，未验证不标成功。
async def verify_restore(url: str, folder: Path, expected: dict[str, Any], verify: Verify) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            actual = await counts(conn)
        if actual != expected["rows"]:
            raise ValueError("恢复表行数不符")
        hashes = await asyncio.to_thread(
            local_snapshot, folder / "files", folder / "restored_files"
        )
        if hashes != expected["files"]:
            raise ValueError("恢复文件摘要不符")
        await verify(url, folder / "restored_files")
    finally:
        await engine.dispose()


# 只清理本框架完成的归档，失败partial不当作可恢复备份。
def expire(root: Path, days: int) -> None:
    older = time.time() - days * 86400
    for folder in root.glob("backup-*"):
        if folder.is_symlink() or not (folder / "verified.json").is_file():
            continue
        if folder.stat().st_mtime < older:
            shutil.rmtree(folder)


# 每次独立空间；恢复失败保留原备份和失败事实，不清理历史可用备份。
async def backup(settings: Any, verify: Verify) -> dict[str, Any]:
    root = Path(settings.operations.backup_root).resolve()
    folder = root / ("backup-" + str(int(time.time())) + "-" + secrets.token_hex(4))
    folder.mkdir(parents=True)
    started = time.time()
    pg_bin = settings.operations.pg_bin
    expected = await snapshot(settings.database_url, folder, pg_bin)
    expected["files"] = await files_snapshot(settings, folder / "files")
    expected["started_at"], expected["files_finished_at"] = started, time.time()
    (folder / "manifest.json").write_text(json.dumps(expected, indent=2))
    if make_url(settings.database_url).get_backend_name() == "postgresql":
        await postgres_restore(settings.database_url, folder, verify, expected, pg_bin)
    else:
        shutil.copyfile(folder / "database.db", folder / "restore.db")
        await verify_restore(
            "sqlite+aiosqlite:///" + str(folder / "restore.db"), folder, expected, verify
        )
    (folder / "verified.json").write_text(
        json.dumps(dict(ready=True, rows=True, migration=True, files=True, verified_at=time.time()))
    )
    await asyncio.to_thread(expire, root, settings.operations.backup_days)
    return dict(
        archive=folder.name,
        verified=True,
        tables=len(expected["rows"]),
        files=len(expected["files"]),
        elapsed_ms=(time.time() - started) * 1000,
    )
