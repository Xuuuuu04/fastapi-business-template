import asyncio
import json
import os
import subprocess
import sys

from fastapi_check.check import execute
from fastapi_check.matrix import CheckOptions
from fastapi_check.quality.rules import PROJECT
from fastapi_project.development.check_assets import atomic_bytes
from fastapi_project.development.evidence import full_check_current
from fastapi_project.development.history import fingerprints, read_checks
from fastapi_project.development.migration_merge import migration_plan, write_merge
from fastapi_project.development.migration_verify import verify
from fastapi_project.development.selection import Selection


def stage(name: str) -> None:
    atomic_bytes(
        PROJECT / ".agents/records/integration-stage.json", json.dumps({"stage": name}).encode()
    )


def command(name: str, *arguments: str) -> None:
    script = "from fastapi_dev.main import main; main()"
    result = subprocess.run(
        [sys.executable, "-c", script, name, *arguments], cwd=PROJECT / "server", check=False
    )
    if result.returncode:
        raise ValueError("整合阶段命令没有通过：" + name)


def migrations(postgres: str) -> dict | None:
    plan = migration_plan(PROJECT)
    if len(plan["heads"]) <= 1:
        return None
    generated = write_merge(PROJECT, plan)
    if generated is None or not plan["anchor"]:
        raise ValueError("多头迁移没有生成可验证的增量合并")
    return asyncio.run(verify(PROJECT, plan["anchor"], postgres)) | {
        "merge_file": generated.relative_to(PROJECT / "server").as_posix()
    }


def format_generated(migration: dict | None) -> None:
    stage("format")
    paths = ["app/setup/catalog.py", "app/api/routers.py"]
    if migration:
        paths.append(migration["merge_file"])
    subprocess.run([sys.executable, "-m", "ruff", "check", *paths, "--fix"], check=True)
    subprocess.run([sys.executable, "-m", "ruff", "format", *paths], check=True)


def checked_record(postgres: str) -> dict:
    before = {record["id"] for record in read_checks(PROJECT, include_cases=False)}
    stage("dual-database-check")
    workers = int(os.environ.get("FASTAPI_MERGE_WORKERS", "4"))
    execute(Selection(), postgres, CheckOptions(database="both", workers=workers, delivery=True))
    records = [
        record for record in read_checks(PROJECT, include_cases=False) if record["id"] not in before
    ]
    from app.setup.application import application_modules
    from shared.modules.catalog import Catalog

    catalog = Catalog(application_modules())
    versions = fingerprints(PROJECT, list(catalog.modules), catalog.links())
    if (
        len(records) != 1
        or not records[0]["passed"]
        or not full_check_current(records[0], versions, PROJECT)
    ):
        raise ValueError("缺少本次当前源码完整成功证据")
    if {suite["database"] for suite in records[0]["suites"] if suite["exit_code"] == 0} != {
        "sqlite",
        "postgresql",
    }:
        raise ValueError("本次双库结果不完整")
    return records[0]


def main() -> None:
    postgres = os.environ.get("FASTAPI_MERGE_POSTGRES", "")
    if not postgres:
        raise ValueError("整合需要显式隔离PostgreSQL控制连接")
    stage("migrations")
    migration = migrations(postgres)
    format_generated(migration)
    stage("framework-integrity")
    command("framework-lock")
    stage("documents")
    command("docs")
    record = checked_record(postgres)
    result = {"passed": True, "check": record["id"], "migration": migration}
    atomic_bytes(
        PROJECT / ".agents/records/integration-result.json",
        json.dumps(result, ensure_ascii=False).encode(),
    )
    stage("ready")


if __name__ == "__main__":
    main()
