import json

from shared.data.models import Data
from shared.errors.framework import StepRuleBroken
from shared.remote_calls.endpoint import Endpoint
from shared.remote_calls.request import FilePart, RemoteRequest
from shared.remote_calls.routing import render_path, routing_problems


def request_for(
    endpoint: Endpoint, input: Data, key: str = "", files: tuple[FilePart, ...] = ()
) -> RemoteRequest:
    problems = routing_problems(endpoint)
    if problems:
        raise StepRuleBroken("；".join(problems))
    parsed = endpoint.input.model_validate(input)
    payload = parsed.model_dump(mode="json")
    path = render_path(endpoint.path, payload, endpoint.path_fields)
    leftover = set(payload) - set(endpoint.path_fields) - set(endpoint.query_fields)
    query = set(endpoint.query_fields)
    body = set(endpoint.body_fields) if endpoint.body_fields is not None else leftover
    if endpoint.method in {"GET", "HEAD"} and endpoint.body_fields is None:
        query |= body
        body = set()
    params = {alias(endpoint, name): payload[name] for name in sorted(query)}
    content = {alias(endpoint, name): payload[name] for name in sorted(body)}
    check_files(endpoint, files)
    form = (
        {
            name: value if isinstance(value, str) else json.dumps(value)
            for name, value in content.items()
        }
        if files
        else None
    )
    return RemoteRequest(
        endpoint.method,
        path,
        params=params or None,
        json=content if not files and endpoint.method not in {"GET", "HEAD"} else None,
        key=key,
        accepted_statuses=endpoint.accepted_statuses,
        endpoint=endpoint.name,
        effect=endpoint.effect,
        unknown_on=endpoint.unknown_on,
        protocol=endpoint,
        input=parsed,
        files=files,
        form=form,
    )


def alias(endpoint: Endpoint, name: str) -> str:
    field = endpoint.input.model_fields.get(name)
    return (field.serialization_alias or field.alias or name) if field else name


def check_files(endpoint: Endpoint, files: tuple[FilePart, ...]) -> None:
    names = [part.field for part in files]
    if len(names) != len(set(names)) or set(names) != set(endpoint.file_fields):
        raise StepRuleBroken("传输文件与Endpoint.file_fields声明不一致")
    if set(names) & {alias(endpoint, name) for name in endpoint.input.model_fields}:
        raise StepRuleBroken("文件字段与普通输入字段重名")
    if sum(len(part.content) for part in files) > endpoint.max_upload_bytes:
        raise StepRuleBroken("上传文件超过声明上限")
    if any(
        not part.filename
        or len(part.filename) > 200
        or any(char in part.filename for char in "\r\n/\\")
        for part in files
    ):
        raise StepRuleBroken("上传文件名必须是有界文件名")
    if any(
        len(part.content_type) > 100 or "\r" in part.content_type or "\n" in part.content_type
        for part in files
    ):
        raise StepRuleBroken("上传内容类型无效")
