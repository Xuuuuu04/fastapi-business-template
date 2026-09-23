"""
附件上传、查询、下载和删除接口；组织授权由文件模块执行。
"""

from collections.abc import AsyncIterator
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Request, Response, UploadFile
from fastapi.responses import StreamingResponse

from app.api.identity import require
from app.api.replies import responses_for
from app.api.runner import RunDep
from service.file_library import public as library

router = APIRouter(prefix="/api/v1/files", tags=["文件管理"])


# 分块读取上传正文，避免一次把文件放进内存。
async def upload_chunks(upload: UploadFile) -> AsyncIterator[bytes]:
    while chunk := await upload.read(64 * 1024):
        yield chunk


# 先保存临时上传，再由模块登记文件并核对组织。
@router.post(
    "/{org_id}",
    summary="上传文件",
    operation_id="save_file",
    response_model=library.FileView,
    responses=responses_for(library.save_file),
)
async def save_file(
    org_id: str, request: Request, run: RunDep, upload: Annotated[UploadFile, File()]
) -> library.FileView:
    require(run.caller, library.save_file.access)
    area = request.app.state.services.uploads
    received = await area.receive(upload.filename or "file", upload_chunks(upload))
    try:
        return await run(
            library.save_file, library.SaveInput(org_id=org_id, temp_id=received.temp_id)
        )
    finally:
        await area.discard(received.temp_id)


# 查询一个组织中未删除的文件。
@router.get(
    "/{org_id}",
    summary="查询文件",
    operation_id="list_files",
    response_model=library.FileList,
    responses=responses_for(library.list_files),
)
async def list_files(org_id: str, run: RunDep) -> library.FileList:
    return await run(library.list_files, library.OrgQuery(org_id=org_id))


# 返回经组织核对后的文件信息，不公开存储键。
@router.get(
    "/{org_id}/{file_id}/info",
    summary="文件信息",
    operation_id="get_file_info",
    response_model=library.FileView,
    responses=responses_for(library.get_file),
)
async def get_file_info(org_id: str, file_id: str, run: RunDep) -> library.FileView:
    entry = await run(library.get_file, library.FileQuery(org_id=org_id, file_id=file_id))
    return entry.view


# 授权后按块返回内容，并要求浏览器作为附件下载。
@router.get(
    "/{org_id}/{file_id}/download",
    summary="下载文件",
    operation_id="download_file",
    responses=responses_for(library.get_file),
)
async def download_file(
    org_id: str, file_id: str, request: Request, run: RunDep
) -> StreamingResponse:
    entry = await run(library.get_file, library.FileQuery(org_id=org_id, file_id=file_id))
    storage = request.app.state.services.runtime.files
    name = quote(entry.view.name, safe="")
    return StreamingResponse(
        storage.open(entry.key),
        media_type=entry.view.content_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{name}"},
    )


# 标记文件为待清理，后续立即不能下载。
@router.delete(
    "/{org_id}/{file_id}",
    summary="删除文件",
    operation_id="delete_file",
    status_code=204,
    responses=responses_for(library.delete_file),
)
async def delete_file(org_id: str, file_id: str, run: RunDep) -> Response:
    await run(library.delete_file, library.FileQuery(org_id=org_id, file_id=file_id))
    return Response(status_code=204)
