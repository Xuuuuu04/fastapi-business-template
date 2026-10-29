import traceback

from shared.errors.kinds import BusinessError

MAX_ERROR_TEXT = 4000


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
