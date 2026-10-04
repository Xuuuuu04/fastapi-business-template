"""
计算当前实际运行代码的摘要，区分旧版本成功样例与当前版本成功样例。
服务创建时计算一次；不包含环境、数据库、文档、测试和运行记录，也不逐请求读取文件。
"""

import hashlib
from pathlib import Path


# 路径相对于 server/，本地目录与部署镜像中的相同源码得到相同结果。
def source_version(root: Path) -> str:
    paths = {root / "pyproject.toml", root / "uv.lock"}
    for area in ("app", "service", "shared", "tools", "migrations"):
        paths |= set((root / area).rglob("*.py"))
        paths |= set((root / area).rglob("module.json"))
    digest = hashlib.sha256()
    for path in sorted(paths):
        if path.is_file() and "__pycache__" not in path.parts:
            digest.update(path.relative_to(root).as_posix().encode() + b"\0")
            digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()
