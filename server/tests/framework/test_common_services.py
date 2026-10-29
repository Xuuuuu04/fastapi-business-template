from typing import Any, cast

import httpx2
import pytest
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    delete,
    func,
    insert,
    or_,
    select,
    text,
    update,
)

from shared.access.caller import Caller
from shared.cache.backends import MemoryCache
from shared.cache.gate import ModuleCache
from shared.db.access import Db, is_write
from shared.db.org import check_org, org_column
from shared.errors.framework import RemoteResultUnknown, StepRuleBroken
from shared.records.models import RemoteCallRecord
from shared.remote_calls.remote import Remote, RemoteConfig
from shared.remote_calls.service import RemoteRequest, RemoteService

probe = MetaData()
files = Table("org_probe_files", probe, Column("id", String(32), primary_key=True), org_column())
links = Table(
    "org_probe_links", probe, Column("id", Integer, primary_key=True), Column("file", String(32))
)


@pytest.mark.anyio
async def test_remote_retry_rules() -> None:
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        if len(seen) in (1, 3, 4):
            return httpx2.Response(503)
        return httpx2.Response(200, json={"ok": True})

    target = Remote("upstream", "上游", retries=1)
    service = RemoteService(
        {"upstream": RemoteConfig(base_url="https://example.com")},
        {"upstream": httpx2.MockTransport(respond)},
        retry_waits=(0.0,),
    )
    try:
        records: list[RemoteCallRecord] = []
        reply = await service.send(target, RemoteRequest("GET", "/items"), records)
        assert reply.data == {"ok": True}
        assert records[0].retries == 1
        with pytest.raises(RemoteResultUnknown):
            await service.send(target, RemoteRequest("POST", "/items", json={"n": 1}), records)
        assert len(seen) == 3
        reply = await service.send(
            target, RemoteRequest("POST", "/items", key="request-1"), records
        )
        assert reply.status == 200
        assert seen[-1].headers["Idempotency-Key"] == "request-1"
        assert records[-1].retries == 1
    finally:
        await service.close()


@pytest.mark.anyio
async def test_remote_write_timeout_result_unknown() -> None:
    def timeout(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("upstream timeout")

    target = Remote("upstream", "上游")
    service = RemoteService(
        {"upstream": RemoteConfig(base_url="https://example.com")},
        {"upstream": httpx2.MockTransport(timeout)},
    )
    try:
        with pytest.raises(RemoteResultUnknown):
            await service.send(target, RemoteRequest("POST", "/items"), [])
    finally:
        await service.close()


@pytest.mark.anyio
async def test_remote_write_read_error_result_unknown() -> None:
    attempts = 0

    def broken_reply(request: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        raise httpx2.ReadError("connection closed")

    target = Remote("upstream", "上游", retries=2)
    service = RemoteService(
        {"upstream": RemoteConfig(base_url="https://example.com")},
        {"upstream": httpx2.MockTransport(broken_reply)},
        retry_waits=(0.0, 0.0),
    )
    try:
        with pytest.raises(RemoteResultUnknown):
            await service.send(target, RemoteRequest("POST", "/items"), [])
        assert attempts == 1
    finally:
        await service.close()


@pytest.mark.anyio
async def test_cache_isolation_and_expiry() -> None:
    backend = MemoryCache()
    first, second = ModuleCache(backend, "first", None), ModuleCache(backend, "second", None)
    await first.set_text("item", "value", 0.01)
    assert await second.get_text("item") is None
    assert await first.get_text("item") == "value"
    with pytest.raises(StepRuleBroken):
        await first.set_text("item", "value", 0)
    await backend.set("expired", "value", 0)
    assert await backend.get("expired") is None


def test_org_filter_checks_every_branch() -> None:
    caller = Caller("1", "user", "北区用户", frozenset(), "north")
    check_org(select(files).where(files.c.org_id == "north"), caller)
    with pytest.raises(StepRuleBroken):
        check_org(select(files), caller)
    with pytest.raises(StepRuleBroken):
        check_org(select(files).where(or_(files.c.org_id == "north", files.c.id == "x")), caller)
    with pytest.raises(StepRuleBroken):
        check_org(update(files).where(files.c.org_id == "north").values(org_id="south"), caller)


def test_org_filter_checks_nested_queries() -> None:
    caller = Caller("1", "user", "北区用户", frozenset(), "north")
    other = files.alias("other")
    count_all = select(func.count()).select_from(files).scalar_subquery()
    count_own = select(func.count()).select_from(files).where(files.c.org_id == "north")
    own = files.c.org_id == "north"
    check_org(select(files.c.id, count_own.scalar_subquery()).where(own), caller)
    check_org(select(other).where(other.c.org_id == "north"), caller)
    with pytest.raises(StepRuleBroken):
        check_org(select(files.c.id, count_all).where(own), caller)
    with pytest.raises(StepRuleBroken):
        check_org(select(files, other).join(other, other.c.id == files.c.id).where(own), caller)
    with pytest.raises(StepRuleBroken):
        check_org(select(links).where(links.c.file.in_(select(files.c.id))), caller)
    with pytest.raises(StepRuleBroken):
        check_org(update(links).where(links.c.file == files.c.id).values(file="x"), caller)


def test_business_db_rejects_sql_text() -> None:
    caller = Caller("1", "user", "北区用户", frozenset(), "north")
    db = Db(cast(Any, None), read_only=True, place="查询", caller=caller)
    with pytest.raises(StepRuleBroken):
        db._check(text("SELECT * FROM file_library_files"))


def test_write_hidden_in_query_is_detected() -> None:
    removed = delete(links).returning(links.c.id).cte("removed")
    assert is_write(select(removed.c.id))
    assert is_write(select(links.c.id).add_cte(insert(links).values(id=1).cte("added")))
    assert is_write(text("WITH gone AS (DELETE FROM t RETURNING id) SELECT id FROM gone"))
    assert not is_write(text("WITH kept AS (SELECT id FROM t) SELECT id FROM kept"))
    assert not is_write(select(links.c.id))
