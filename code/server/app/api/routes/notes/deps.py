"""
取得启动层已经注入的笔记入口。
接口层不导入组装文件或创建具体存储。
"""

from collections.abc import Iterator

from fastapi import Request

from service.notes.public import Notes


# 在请求结束时释放注入的业务资源。
def notes(request: Request) -> Iterator[Notes]:
    with request.app.state.notes() as service:
        yield service
