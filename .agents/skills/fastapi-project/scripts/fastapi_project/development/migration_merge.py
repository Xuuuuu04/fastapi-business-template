"""
多头迁移先检查对象读写影响，独立分支生成增量合并版本，原有迁移不重写。
"""

import hashlib
import uuid
from dataclasses import asdict
from pathlib import Path

from fastapi_project.development.check_assets import atomic_bytes
from fastapi_project.development.migration_graph import branches, read_graph
from fastapi_project.development.migration_operations import Touch, analyze
from fastapi_template.template.files import safe_path


# 同表同对象或整表操作相交，至少一边写入时就不能当作独立变化。
def overlap(first: Touch, second: Touch) -> bool:
    return (
        first.table == second.table
        and (first.object == second.object or "*" in {first.object, second.object})
        and "write" in {first.access, second.access}
    )


# 单分支内部顺序由已有迁移图负责，这里只比较不同头的新增对象影响。
def migration_plan(project: Path) -> dict:
    graph = read_graph(project)
    heads, anchor, split = branches(graph)
    touches: dict[str, list[Touch]] = {}
    unknown = []
    for head, revisions in split.items():
        touches[head] = []
        for revision in revisions:
            actual, questions = analyze(revision)
            touches[head] += actual
            unknown += questions
    conflicts = []
    for number, head in enumerate(heads):
        for other in heads[number + 1 :]:
            conflicts += [
                {"heads": [head, other], "first": asdict(first), "second": asdict(second)}
                for first in touches.get(head, [])
                for second in touches.get(other, [])
                if overlap(first, second)
            ]
    return {
        "heads": heads,
        "anchor": anchor,
        "branches": {
            head: [revision.id for revision in revisions] for head, revisions in split.items()
        },
        "touches": {head: [asdict(touch) for touch in values] for head, values in touches.items()},
        "conflicts": conflicts,
        "unknown": sorted(set(unknown)),
        "mergeable": len(heads) > 1 and not conflicts and not unknown,
        "fingerprints": {
            name: hashlib.sha256(revision.path.read_bytes()).hexdigest()
            for name, revision in graph.items()
        },
    }


# 空合并版本只连接已验证独立的头，不能掩盖未知SQL或对同对象的竞争改动。
def write_merge(project: Path, expected: dict) -> Path | None:
    current = migration_plan(project)
    if current != expected:
        raise ValueError("迁移在分析后发生变化，请重新分析")
    if len(current["heads"]) <= 1:
        return None
    if not current["mergeable"]:
        raise ValueError("迁移包含对象冲突或未知DDL，请先处理后再合并")
    identity = uuid.uuid4().hex[:12]
    path = safe_path(project, "server/migrations/versions/" + identity + "_merge_heads.py")
    text = (
        '"""\n独立迁移分支的增量合并；已有迁移和业务数据操作保持原样。\n"""\n\n'
        f"revision = {identity!r}\ndown_revision = {tuple(current['heads'])!r}\n"
        "branch_labels = None\ndepends_on = None\n\n"
        "# 结构变化已经由各分支负责，合并版本只连接图。\ndef upgrade() -> None:\n    pass\n\n"
        "# 回退时交还两个原头，不删除已有迁移。\ndef downgrade() -> None:\n    pass\n"
    )
    atomic_bytes(path, text.encode())
    return path
