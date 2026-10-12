"""
规则和变化文档只维护明确的账本生成段；段外历史文字保留，边界损坏时拒绝覆盖。
"""

import re
from pathlib import Path


# 生成边界必须成对且唯一，不能把不完整边界之后的手写内容误当生成内容。
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


# 历史规则采纳和三方整合只读取段外文字，不把派生摘要再次当成人类规则。
def manual_text(source: str, kind: str) -> str:
    span = bounds(source, kind)
    if span is None:
        return source
    return source[: span[0]] + source[span[1] :]


# Markdown表格中的脱敏说明保持在一个单元格，不引入另一张业务规则表。
def cell(source: str) -> str:
    return re.sub(r"\s+", " ", source).replace("|", "\\|")


# 第一次只追加生成段，后续只替换同一段，不修改已有规则和手写变化记录。
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
