import json

import httpx2
import pytest
from pydantic import ConfigDict

from shared.errors.framework import RemoteResultUnknown, StepRuleBroken
from shared.public import Data, Endpoint, FilePart, meaning, remote
from shared.remote_calls.endpoint import endpoint_problems
from shared.remote_calls.gate import RemoteGate
from shared.remote_calls.remote import RemoteConfig
from shared.remote_calls.serialization import request_for
from shared.remote_calls.service import RemoteService


class Input(Data):
    record_id: str = meaning("上游记录标识")
    dry_run: bool = meaning("是否试运行")
    title: str = meaning("业务名称")


class Receipt(Data):
    external_id: str | None = meaning("上游编号", default=None, empty="本次响应未提供编号")


endpoint = Endpoint(
    "synthetic.write",
    "POST",
    "/records/{record_id}",
    Input,
    Receipt,
    "write",
    path_fields=("record_id",),
    query_fields=("dry_run",),
    body_fields=("title",),
    receipt_fields=("external_id",),
)


def test_open_empty_protocol_is_explicitly_partial() -> None:
    class Raw(Data):
        model_config = ConfigDict(extra="allow")

    loose = Endpoint("synthetic.raw", "GET", "/raw", Raw, Raw, "read")
    assert not loose.shape()["validation"]["complete"]
    assert endpoint_problems(endpoint) == []
    with pytest.raises(StepRuleBroken, match="路径参数"):
        request_for(endpoint, Input(record_id="..", dry_run=False, title="body"))


@pytest.mark.anyio
async def test_typed_locations_and_missing_receipt() -> None:
    seen = []

    def reply(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"external_id": "ref"} if len(seen) == 1 else {})

    target = remote("synthetic", "合成上游", retries=0)
    service = RemoteService(
        {target.name: RemoteConfig(base_url="https://synthetic.invalid")},
        {target.name: httpx2.MockTransport(reply)},
    )
    records = []
    gate = RemoteGate(service, (target,), records, "传输", endpoints=(endpoint,))
    try:
        request = Input(record_id="private-id", dry_run=True, title="body")
        result = await gate.call(target, endpoint, request)
        assert result.data.external_id == "ref"
        assert seen[0].url.path == "/records/private-id" and seen[0].url.params["dry_run"] == "true"
        assert json.loads(seen[0].content) == {"title": "body"}
        assert records[0].path == "/records/{record_id}"
        with pytest.raises(RemoteResultUnknown, match="关键回执"):
            await gate.call(target, endpoint, request)
        assert records[-1].outcome == "unknown"
    finally:
        await service.close()


@pytest.mark.anyio
async def test_declared_multipart_and_file_limit() -> None:
    from dataclasses import replace

    upload = replace(endpoint, file_fields=("attachment",), max_upload_bytes=4)
    seen = []

    def reply(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"external_id": "ref"})

    target = remote("synthetic", "合成上游", retries=0)
    service = RemoteService(
        {target.name: RemoteConfig(base_url="https://synthetic.invalid")},
        {target.name: httpx2.MockTransport(reply)},
    )
    gate = RemoteGate(service, (target,), [], "文件", endpoints=(upload,))
    input = Input(record_id="record", dry_run=False, title="body")
    try:
        await gate.call(target, upload, input, files=(FilePart("attachment", "data.txt", b"1234"),))
        assert "multipart/form-data" in seen[0].headers["content-type"]
        assert b'name="attachment"' in seen[0].content and b"1234" in seen[0].content
        with pytest.raises(StepRuleBroken, match="超过"):
            await gate.call(
                target, upload, input, files=(FilePart("attachment", "data.txt", b"12345"),)
            )
        assert len(seen) == 1
    finally:
        await service.close()
