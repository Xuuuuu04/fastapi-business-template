"""
迁移保护与真实双库分段导入对账，覆盖兼容提醒和失败回滚。
"""

import time
from dataclasses import replace
from pathlib import Path

import pytest
from alembic.autogenerate import produce_migrations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Column, Integer, MetaData, Table, func, select

from app.setup.build import build
from app.setup.catalog import MODULES
from shared.access.caller import SYSTEM
from shared.config.settings import Settings
from shared.db.ownership import check_migrations, ownership
from shared.errors.framework import DeclarationError
from shared.graphs.observed import run_graph
from shared.graphs.static import flow_graph
from shared.jobs.views import get_job
from shared.jobs.worker import Worker, WorkerOptions
from shared.modules.catalog import Catalog
from shared.records.stores import RunFilter
from tests.framework.import_sample import Input, module, operation, rows, sample_metadata
from tests.testing_app import make_settings, prepare_test_database


# 历史drop/rename、批量改列、命名参数与原始SQL都有明确位置；默认兼容。
def test_history_scan(tmp_path: Path, caplog) -> None:
    versions = tmp_path / "migrations" / "versions"
    versions.mkdir(parents=True)
    (versions / "old.py").write_text("""from alembic import op
def upgrade():
    op.drop_table(table_name="legacy")
    op.rename_table("other", "renamed")
    with op.batch_alter_table("old") as batch:
        batch.alter_column("amount", type_=None)
    op.execute("DROP TABLE hidden")
    from alembic.op import drop_table as remove_table
    remove_table("direct_import")
""")
    assert check_migrations(tmp_path, [], Settings()) == []
    assert "legacy" in caplog.text and "APP_MIGRATION_STRICT" in caplog.text
    errors = check_migrations(tmp_path, [], Settings(migration_strict=True))
    assert len(errors) == 5
    assert "old" in errors[2] or any("old 未登记" in e for e in errors)
    assert (
        len(
            check_migrations(
                tmp_path,
                [],
                Settings(
                    migration_strict=True,
                    owned_tables=["legacy", "other", "old", "direct_import"],
                ),
            )
        )
        == 1
    )


# 只比较本样例创建的表，共享PostgreSQL中其他测试表不属于本次反例。
def compare_owned(sync, options):
    context = MigrationContext.configure(
        sync,
        opts={
            "include_object": options.include_object,
            "include_name": lambda name, kind, parents: (
                kind != "table" or name == "unregistered_history"
            ),
        },
    )
    return produce_migrations(context, MetaData()).upgrade_ops.as_diffs()


# 未登记表不能删除；external只保留，owned历史表才允许显式迁移管理。
@pytest.mark.anyio
async def test_autogenerate_refuses_unknown(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    await prepare_test_database(settings.database_url)
    services = build(settings, modules=[])
    extra = MetaData()
    Table("unregistered_history", extra, Column("id", Integer, primary_key=True))
    try:
        async with services.database.write() as connection:
            await connection.run_sync(extra.create_all)

            with pytest.raises(ValueError, match="unregistered_history"):
                await connection.run_sync(compare_owned, ownership(MODULES, settings))
            excluded = await connection.run_sync(
                compare_owned,
                ownership(
                    MODULES,
                    settings.model_copy(
                        update={"external_tables": ["unregistered_history"]},
                    ),
                ),
            )
            assert not any("unregistered_history" in str(item) for item in excluded)
            owned = await connection.run_sync(
                compare_owned,
                ownership(
                    MODULES,
                    settings.model_copy(
                        update={"owned_tables": ["unregistered_history"]},
                    ),
                ),
            )
            assert any("unregistered_history" in str(item) for item in owned)
    finally:
        async with services.database.write() as connection:
            await connection.run_sync(extra.drop_all)
        await services.close()


# 非分段、空来源和未登记目标在启动前就发现。
def test_import_declarations() -> None:
    job = module.jobs[0]
    with pytest.raises(DeclarationError, match="segmented"):
        Catalog([replace(module, jobs=(replace(job, segmented=False),))])
    with pytest.raises(DeclarationError, match="预期行数"):
        bad = replace(job.import_plan, reconcile=replace(job.import_plan.reconcile, rows=0))
        Catalog([replace(module, jobs=(replace(job, import_plan=bad),))])
    with pytest.raises(DeclarationError, match="目标表"):
        Catalog([replace(module, tables=())])


# 一次通过；少行、质量缺失和引用缺失均失败，已经提交的第一批保留。
@pytest.mark.anyio
@pytest.mark.parametrize(
    "fault,failed",
    [
        (None, None),
        ("omit", "rows"),
        ("bad_quality", "non_null:quality"),
        ("bad_reference", "reference:parent_id"),
        ("changed_plan", "import_source_changed"),
    ],
)
async def test_import_reconciliation(tmp_path: Path, fault: str | None, failed: str | None) -> None:
    settings = make_settings(tmp_path, run_records="database")
    await prepare_test_database(settings.database_url)
    services = build(settings, modules=[module])
    async with services.database.write() as connection:
        await connection.run_sync(sample_metadata.drop_all)
        await connection.run_sync(sample_metadata.create_all)
    try:
        input = Input(**({fault: True} if fault and fault != "changed_plan" else {}))
        job_id = await services.runtime.submit(operation, input, caller=SYSTEM)
        assert await services.runtime.submit(operation, input, caller=SYSTEM) == job_id
        if fault == "changed_plan":
            job = module.jobs[0]
            changed = replace(job.import_plan, source_revision="new-source")
            services.runtime.catalog = Catalog(
                [replace(module, jobs=(replace(job, import_plan=changed),))]
            )
        ticket = await services.queue.claim(time.time())
        assert ticket is not None
        await Worker(services.runtime, services.queue, [], WorkerOptions()).execute(ticket)
        job = await get_job(services.database, job_id)
        if fault == "changed_plan":
            assert job is not None and job.state == "blocked"
            assert await services.recorder.store.recent(RunFilter(job_id=job_id), 10) == []
            return
        assert job is not None and job.state == ("failed" if failed else "done")
        await services.recorder.flush()
        runs = await services.recorder.store.recent(RunFilter(job_id=job_id), 10)
        last = next(run for run in runs if run.segment_number == 2)
        assert last.import_report["status"] == ("失败" if failed else "通过")
        if failed:
            assert last.import_report["checks"][failed]["passed"] is False
            assert last.writes == "rolled_back"
        assert "导入对账" in run_graph(runs)
        assert "最后一批提交前对账" in flow_graph(services.catalog.binding(operation))
        async with services.database.read() as connection:
            count = (await connection.execute(select(func.count()).select_from(rows))).scalar_one()
        assert count == (1 if failed else 2)
    finally:
        async with services.database.write() as connection:
            await connection.run_sync(sample_metadata.drop_all)
        await services.close()
