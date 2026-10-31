from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

from app.api.identity_resolver import resolve_session
from shared.errors.details import public_message
from shared.errors.framework import InvalidInput, StepRuleBroken
from shared.graphs.observed import external_nodes
from shared.public import Data, meaning
from shared.records.models import RemoteCallRecord, StepRecord
from shared.records.recorder import Recorder
from shared.records.stores import RunFilter
from tests.contracts.test_run_stores import make_run
from tests.framework.test_recorder import SlowStore


@pytest.mark.anyio
async def test_recent_merges_by_start_time_and_keeps_live_version() -> None:
    store = SlowStore()
    recorder = Recorder(store)
    recent = make_run("new", "new", 200)
    stale = make_run("live", "live", 100, "running")
    await store.save([recent, stale])
    recorder.start(stale)
    pending = make_run("pending", "pending", 150)
    await recorder.finish(pending)
    assert [run.id for run in await recorder.recent(RunFilter(), 2)] == ["new", "pending"]
    assert (await recorder.recent(RunFilter(), 3))[-1].status == "running"


@pytest.mark.parametrize(
    ("outcome", "provider", "expected"),
    [
        ("ok", "completed", "ok"),
        ("ok", "accepted", "ok"),
        ("failed", "refused", "failed"),
        ("unknown", "unknown", "running"),
    ],
)
def test_effect_graph_reports_provider_result(outcome: str, provider: str, expected: str) -> None:
    part = StepRecord("s", "send", "发送", "remote", "x.py:1", status="running")
    part.remotes = [
        RemoteCallRecord("mail", "smtp", "intent", 0, 0, outcome=outcome, provider_state=provider)
    ]
    assert external_nodes("s", part)[0].endswith(":::" + expected)


def test_public_errors_preserve_business_rules_and_hide_framework_detail() -> None:
    assert public_message(InvalidInput("数量必须大于零")) == "数量必须大于零"
    assert "private" not in public_message(StepRuleBroken("private"))


class SessionInput(Data):
    token: str = meaning("令牌", secret=True)


@pytest.mark.anyio
async def test_identity_run_has_request_id() -> None:
    identity = SimpleNamespace(username="user", name="测试", permissions=[], org_id="test")
    run = AsyncMock(return_value=identity)
    services = SimpleNamespace(
        catalog=SimpleNamespace(identity=SimpleNamespace(input=SessionInput)),
        runtime=SimpleNamespace(run=run),
    )
    app = SimpleNamespace(state=SimpleNamespace(services=services))
    request = Request({"type": "http", "app": app, "state": {"request_id": "request-test"}})
    await resolve_session(request, "synthetic-token")
    assert run.call_args.kwargs["request_id"] == "request-test"
    assert "on_start" not in run.call_args.kwargs


def test_finished_unknown_effect_is_not_successful() -> None:
    part = StepRecord("s", "send", "发送", "remote", "x.py:1", status="failed")
    part.remotes = [
        RemoteCallRecord(
            "mail", "smtp", "intent", 0, 3, outcome="unknown", provider_state="unknown"
        )
    ]
    assert external_nodes("s", part)[0].endswith(":::failed")
