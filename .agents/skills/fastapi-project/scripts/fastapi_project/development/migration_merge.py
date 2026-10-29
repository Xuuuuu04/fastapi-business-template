import hashlib
import uuid
from dataclasses import asdict
from pathlib import Path

from fastapi_project.development.check_assets import atomic_bytes
from fastapi_project.development.migration_graph import branches, read_graph
from fastapi_project.development.migration_operations import Touch, analyze
from fastapi_template.template.files import safe_path


def overlap(first: Touch, second: Touch) -> bool:
    return (
        first.table == second.table
        and (first.object == second.object or "*" in {first.object, second.object})
        and "write" in {first.access, second.access}
    )


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
        f"revision = {identity!r}\ndown_revision = {tuple(current['heads'])!r}\n"
        "branch_labels = None\ndepends_on = None\n\n"
        "def upgrade() -> None:\n    pass\n\n"
        "def downgrade() -> None:\n    pass\n"
    )
    atomic_bytes(path, text.encode())
    return path
