import re
from pathlib import Path


def bounds(source: str, kind: str) -> tuple[int, int] | None:
    begin = f"<!-- fastapi-ledger-{kind}:begin -->"
    end = f"<!-- fastapi-ledger-{kind}:end -->"
    if begin not in source and end not in source:
        return None
    if (
        source.count(begin) != 1
        or source.count(end) != 1
        or source.index(end) < source.index(begin)
    ):
        raise ValueError("账本文档生成边界损坏：" + kind)
    return source.index(begin), source.index(end) + len(end)


def manual_text(source: str, kind: str) -> str:
    span = bounds(source, kind)
    if span is None:
        return source
    return source[: span[0]] + source[span[1] :]


def cell(source: str) -> str:
    return re.sub(r"\s+", " ", source).replace("|", "\\|")


def section(path: Path, kind: str, body: str) -> str:
    source = path.read_text() if path.exists() else ""
    block = (
        f"<!-- fastapi-ledger-{kind}:begin -->\n"
        + body.rstrip()
        + f"\n<!-- fastapi-ledger-{kind}:end -->"
    )
    span = bounds(source, kind)
    if span:
        return source[: span[0]] + block + source[span[1] :]
    return source + ("\n\n" if source else "") + block + "\n"
