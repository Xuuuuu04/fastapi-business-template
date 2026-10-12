"""
文档模块索引按行身份合并，表外手写说明仍走三方比较，冲突不覆盖。
"""

import re
from pathlib import Path

from fastapi_project.development.check_assets import atomic_bytes
from fastapi_project.development.integration_json import blob, identity_merge
from fastapi_template.template.merge import merge_text

TOKEN = "@@MODULE_INDEX@@\n"


# 只提取明确模块表，其他段落和标点原样保留作为独立原件。
def split_index(source: str) -> tuple[str, list[dict]]:
    lines = source.splitlines(keepends=True)
    heading = lines.index("## 模块\n")
    start = next(
        number for number in range(heading + 1, len(lines)) if lines[number].startswith("| 模块")
    )
    end = start + 2
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    rows = [{"id": line.split("|")[1].strip(), "text": line} for line in lines[start + 2 : end]]
    return "".join(lines[:start] + [TOKEN] + lines[end:]), rows


# 模块表是可再生索引，表外双方都改时依然需要解决真实文本冲突。
def resolve_index(project: Path, commits: tuple[str, str, str]) -> str | None:
    values = [blob(project, commit, "doc/README.md") for commit in commits]
    if not all(value is not None for value in values):
        return None
    parts = [split_index(value.decode()) for value in values if value is not None]
    rows = identity_merge(parts[0][1], parts[1][1], parts[2][1], "id")
    change = merge_text(
        "doc/README.md", parts[0][0].encode(), parts[1][0].encode(), parts[2][0].encode()
    )
    if change.state == "conflict" or change.content is None:
        raise ValueError("业务文档目录的手写说明存在冲突")
    table = "| 模块 | 名称 | 文档 |\n| --- | --- | --- |\n" + "".join(row["text"] for row in rows)
    target = project / "doc/README.md"
    atomic_bytes(target, change.content.decode().replace(TOKEN, table).encode())
    return "doc/README.md"


# AGENTS仅生成段可再生，其他人写的说明和要求必须保留三方语义。
def resolve_agents(project: Path, commits: tuple[str, str, str]) -> str | None:
    values = [blob(project, commit, "AGENTS.md") for commit in commits]
    if not all(value is not None for value in values):
        return None
    begin, end = "<!-- fastapi-current-state:begin -->", "<!-- fastapi-current-state:end -->"
    pattern = re.escape(begin) + r".*?" + re.escape(end)
    sources = [
        re.sub(pattern, begin + "\n" + end, value.decode(), flags=re.DOTALL)
        for value in values
        if value is not None
    ]
    change = merge_text("AGENTS.md", sources[0].encode(), sources[1].encode(), sources[2].encode())
    if change.state == "conflict" or change.content is None:
        raise ValueError("AGENTS手写要求存在冲突")
    atomic_bytes(project / "AGENTS.md", change.content)
    return "AGENTS.md"
