"""
生成器验收复用依赖和类型增量缓存；每个样例仍生成独立源码及数据库。
缓存由 mypy 按源码、选项和依赖校验，不能作为检查成功证据。
"""

import shutil
from pathlib import Path

from fastapi_template.template.initialization import initialize as initialize_project


# 保留真实初始化路径，仅复制可自行失效的类型缓存，避免每份副本重复分析公共依赖。
def initialize(source: Path, target: Path, name: str) -> None:
    initialize_project(source, target, name)
    cache = source / "server/.mypy_cache"
    if cache.is_dir():
        shutil.copytree(cache, target / "server/.mypy_cache")
