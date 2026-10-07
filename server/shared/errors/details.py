"""意外异常只保留类型和调用位置，不读取异常消息或源码文本。"""

import traceback

from shared.errors.kinds import BusinessError

MAX_ERROR_TEXT = 4000


# 日志保留异常类型、文件、函数和行号；已定义的业务错误继续显示其公开原因。
def safe_exception_text(error: BaseException) -> str:
    title = type(error).__name__
    if isinstance(error, BusinessError):
        title += f"：{error.detail}"
    title = title[:MAX_ERROR_TEXT]
    frames = traceback.StackSummary.extract(
        traceback.walk_tb(error.__traceback__), lookup_lines=False
    )
    places = "\n".join(f"{frame.filename}:{frame.lineno} ({frame.name})" for frame in frames)
    available = MAX_ERROR_TEXT - len(title) - 1
    return title + ("\n" + places[-available:] if places and available > 0 else "")
