from pathlib import Path

import httpx2
import pytest

from shared.errors.framework import (
    FileTooLarge,
    RemoteRejected,
    RemoteResultUnknown,
    StepRuleBroken,
)
from shared.files.gate import ModuleFiles
from shared.files.storage import LocalFiles
from shared.files.uploads import UploadArea
from shared.records.models import RemoteCallRecord
from shared.remote_calls.remote import Remote, RemoteConfig
from shared.remote_calls.service import RemoteRequest, RemoteService

pytestmark = pytest.mark.anyio


async def test_file_inputs_and_generated_output(tmp_path: Path) -> None:
    storage = LocalFiles(tmp_path / "files")
    uploads = UploadArea(tmp_path / "uploads", 100, [".txt"])
    files = ModuleFiles(storage, uploads, "sample_export")

    async def chunks():
        yield b"hello"

    uploaded = await uploads.receive("input.txt", chunks())
    assert await files.read_upload(uploaded.temp_id, 5) == b"hello"
    with pytest.raises(FileTooLarge):
        await files.read_upload(uploaded.temp_id, 4)
    (uploads.root / uploaded.temp_id).write_bytes(b"x" * 50)
    with pytest.raises(FileTooLarge):
        await files.read_upload(uploaded.temp_id, 5)
    await files.discard_upload(uploaded.temp_id)
    assert not (uploads.root / uploaded.temp_id).exists()
    saved = await files.save_bytes("result.txt", b"report")
    assert saved.key == "sample_export/result.txt" and await files.exists("result.txt")
    assert await files.read(saved.key, 6) == b"report"
    with pytest.raises(StepRuleBroken):
        await files.save_bytes("../escape.txt", b"no")


async def test_explicit_409_capture_preserves_default_errors() -> None:
    target = Remote("partner", "合成外部服务", retries=2)
    calls = []

    def reply(request):
        calls.append(request.method)
        return httpx2.Response(409, json={"accepted": False})

    service = RemoteService(
        {target.name: RemoteConfig(base_url="https://synthetic.test")},
        {target.name: httpx2.MockTransport(reply)},
        retry_waits=(0,),
    )
    records: list[RemoteCallRecord] = []
    try:
        received = await service.send(
            target, RemoteRequest("POST", "/jobs", accepted_statuses=(409,)), records
        )
        assert received.status == 409 and received.data == {"accepted": False}
        assert records[-1].outcome == "failed" and len(calls) == 1
        with pytest.raises(RemoteRejected):
            await service.send(target, RemoteRequest("POST", "/jobs"), records)
        assert len(calls) == 2
    finally:
        await service.close()


async def test_captured_reply_does_not_clear_prior_unknown() -> None:
    target = Remote("partner", "合成服务", retries=1)
    count = 0

    def reply(request):
        nonlocal count
        count += 1
        return httpx2.Response(503 if count == 1 else 409, json={"accepted": False})

    service = RemoteService(
        {target.name: RemoteConfig(base_url="https://synthetic.test")},
        {target.name: httpx2.MockTransport(reply)},
        retry_waits=(0,),
    )
    try:
        with pytest.raises(RemoteResultUnknown):
            await service.send(
                target, RemoteRequest("POST", "/jobs", key="fixed", accepted_statuses=(409,)), []
            )
        assert count == 2
    finally:
        await service.close()


@pytest.mark.parametrize("status", [200, 408, 499, 500, 503])
async def test_unknown_status_cannot_be_captured(status) -> None:
    target = Remote("partner", "合成服务")
    service = RemoteService({})
    try:
        with pytest.raises(StepRuleBroken):
            await service.send(
                target, RemoteRequest("POST", "/jobs", accepted_statuses=(status,)), []
            )
    finally:
        await service.close()
