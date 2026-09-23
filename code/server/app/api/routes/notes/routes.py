"""
提供笔记的增删改查接口。
参数与响应处理集中在此，业务规则交给 NoteService。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response

from app.api.access.key import require_key
from app.api.replies.models import ERRORS, Page
from app.api.routes.notes.deps import notes
from app.api.routes.notes.forms import NoteInput, NoteOutput
from service.notes.public import Notes

router = APIRouter(prefix="/api/v1/notes", tags=["笔记"], responses=ERRORS)
Service = Annotated[Notes, Depends(notes)]
NoteId = Annotated[int, Path(gt=0, description="笔记编号")]
write = [Depends(require_key)]


# 返回笔记总数和当前页。
@router.get("", response_model=Page[NoteOutput], summary="查询笔记", operation_id="list_notes")
def list_notes(
    service: Service,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[NoteOutput]:
    total, rows = service.list(offset, limit)
    return Page(
        items=[NoteOutput.model_validate(row) for row in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


# 读取指定笔记的完整内容。
@router.get(
    "/{note_id}", response_model=NoteOutput, summary="读取笔记", operation_id="get_note"
)
def get_note(note_id: NoteId, service: Service) -> NoteOutput:
    return NoteOutput.model_validate(service.get(note_id))


# 创建一条新笔记。
@router.post(
    "",
    response_model=NoteOutput,
    status_code=201,
    dependencies=write,
    summary="创建笔记",
    operation_id="create_note",
)
def create_note(data: NoteInput, service: Service) -> NoteOutput:
    return NoteOutput.model_validate(service.create(data.title, data.body))


# 完整替换指定笔记的标题和正文。
@router.put(
    "/{note_id}",
    response_model=NoteOutput,
    dependencies=write,
    summary="更新笔记",
    operation_id="update_note",
)
def update_note(note_id: NoteId, data: NoteInput, service: Service) -> NoteOutput:
    return NoteOutput.model_validate(service.update(note_id, data.title, data.body))


# 删除指定笔记并返回空响应。
@router.delete(
    "/{note_id}",
    status_code=204,
    dependencies=write,
    summary="删除笔记",
    operation_id="delete_note",
)
def delete_note(note_id: NoteId, service: Service) -> Response:
    service.delete(note_id)
    return Response(status_code=204)
