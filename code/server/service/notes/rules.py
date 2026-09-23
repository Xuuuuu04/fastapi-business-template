"""
定义笔记文本校验规则。
规则是独立纯函数，可通过注册入口记录执行版本和结果状态。
"""

from service.notes.types import InvalidNote


# 整理标题并检查业务输入长度。
def clean(title: str, body: str) -> str:
    title = title.strip()
    if not 1 <= len(title) <= 80 or len(body) > 5000:
        raise InvalidNote("标题需要 1 至 80 个字符，正文最多 5000 个字符")
    return title
