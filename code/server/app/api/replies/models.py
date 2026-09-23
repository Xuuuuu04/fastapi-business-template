"""
定义通用分页和错误响应。
接口文档与实际返回共用这些类型。
"""

from pydantic import BaseModel, Field


class Page[Item](BaseModel):
    items: list[Item]
    total: int
    offset: int
    limit: int


class Issue(BaseModel):
    field: str
    message: str


class Error(BaseModel):
    code: str
    message: str
    request_id: str
    details: list[Issue] = Field(default_factory=list)


ERRORS = {
    status: {"model": Error, "description": message}
    for status, message in {
        401: "缺少或无效的写入密钥",
        404: "记录不存在",
        409: "标题重复",
        422: "参数不符合要求",
        500: "服务器内部错误",
        503: "数据库或写入配置未就绪",
    }.items()
}
