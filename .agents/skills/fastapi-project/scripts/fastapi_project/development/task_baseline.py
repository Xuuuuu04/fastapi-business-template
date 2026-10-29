import difflib
import hashlib
import io
import zipfile
from pathlib import Path

from fastapi_project.development.check_assets import atomic_bytes
from fastapi_project.development.task_models import TaskCard, card_path, source_snapshot
from fastapi_template.template.files import safe_path


def baseline_path(project: Path, identity: str) -> Path:
    card_path(project, identity)
    return project / ".agents/records/task-baselines" / (identity + ".zip")


def save_baseline(project: Path, identity: str, before: dict[str, str]) -> None:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, digest in before.items():
            content = safe_path(project, name).read_bytes()
            if hashlib.sha256(content).hexdigest() != digest:
                raise ValueError("任务开工期间源码变化，请重新生成任务卡")
            archive.writestr(name, content)
    path = baseline_path(project, identity)
    atomic_bytes(path, payload.getvalue())
    path.chmod(0o600)


def review_material(project: Path, card: TaskCard) -> list[str]:
    files = [
        project / "doc" / card.package / "rules.md",
        project / "doc" / card.package / "ledger.md",
    ]
    files += sorted((project / "doc" / card.package / "cases").glob("*.json"))
    lines = []
    for path in files[:12]:
        if path.is_file():
            safe_path(project, path.relative_to(project).as_posix())
            content = path.read_text()
            lines += [
                f"## {path.relative_to(project)}",
                "",
                "````text",
                content[:16000],
                "````",
                "",
            ]
            if len(content) > 16000:
                lines.append("内容超过展示上限，请读取原件。")
    if len(files) > 12:
        lines.append(f"另有{len(files) - 12}份资料，请按样例目录继续读取。")
    return lines


def review_pack(project: Path, card: TaskCard) -> Path:
    path = baseline_path(project, card.id)
    if not path.is_file():
        raise ValueError("旧任务没有原件基线，不能生成准确复核差异")
    current = source_snapshot(project)
    changed = sorted(
        name
        for name in card.before.keys() | current.keys()
        if card.before.get(name) != current.get(name)
    )
    lines = [
        f"# 独立复核资料：{card.package}",
        "",
        *review_material(project, card),
        "## 源码差异",
        "",
    ]
    with zipfile.ZipFile(path) as archive:
        for name in changed:
            before = archive.read(name) if name in card.before else b""
            target = safe_path(project, name)
            after = target.read_bytes() if target.is_file() else b""
            if name in card.before and hashlib.sha256(before).hexdigest() != card.before[name]:
                raise ValueError("任务原件基线摘要不一致，不能生成复核资料")
            diff = difflib.unified_diff(
                before.decode().splitlines(),
                after.decode().splitlines(),
                fromfile="before/" + name,
                tofile="after/" + name,
                lineterm="",
            )
            lines += ["````diff", *diff, "````", ""]
    output = project / ".agents/records/review-packs" / (card.id + ".md")
    atomic_bytes(output, ("\n".join(lines) + "\n").encode())
    output.chmod(0o600)
    return output
