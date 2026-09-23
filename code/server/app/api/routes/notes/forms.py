"""
定义笔记接口的输入和输出。
接口字段说明同时用于全局 API 文档。
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NoteInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"title": "第一条笔记", "body": "检查代码组织方式"}]},
    )

    title: str = Field(min_length=1, max_length=80, description="标题，保存前去除首尾空白")
    body: str = Field(default="", max_length=5000, description="正文，允许为空")


class NoteOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="笔记编号")
    title: str = Field(description="标题，区分大小写且不可重复")
    body: str = Field(description="正文")
    created_at: datetime = Field(description="UTC 创建时间")
