import hashlib
from pathlib import Path


def source_version(root: Path) -> str:
    paths = {root / "pyproject.toml", root / "uv.lock"}
    for area in ("app", "service", "library", "shared", "migrations"):
        paths |= set((root / area).rglob("*.py"))
        paths |= set((root / area).rglob("module.json"))
    digest = hashlib.sha256()
    for path in sorted(paths):
        if path.is_file() and "__pycache__" not in path.parts:
            digest.update(path.relative_to(root).as_posix().encode() + b"\0")
            digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()
