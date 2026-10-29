import shutil
from pathlib import Path

from fastapi_template.template.initialization import initialize as initialize_project


def initialize(source: Path, target: Path, name: str) -> None:
    initialize_project(source, target, name)
    cache = source / "server/.mypy_cache"
    if cache.is_dir():
        shutil.copytree(cache, target / "server/.mypy_cache")
