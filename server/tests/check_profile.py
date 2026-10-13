"""
新产品保留框架集成检查；框架未改变时，模板工具自身的回归由模板仓库负责。
"""

import hashlib
import json
from pathlib import Path


# 只依据复制时的明确来源比较框架，不把本机检查历史或产品版本当成证明。
def product_framework_unchanged(root: Path) -> bool:
    from shared.modules.validation.framework_lock import differences

    path = root / "template-source.json"
    if not path.is_file():
        return False
    try:
        recorded = json.loads(path.read_text(encoding="utf-8"))
        lock = root / "server/framework.lock"
        # 旧来源没有锁文件摘要时保守执行；升级后才可沿用模板验证。
        if recorded.get("framework_lock") != hashlib.sha256(lock.read_bytes()).hexdigest():
            return False
        if differences(root / "server"):
            return False
        # 来源只记录模板管理文件，不包含产品源码、依赖与迁移历史。
        files = recorded.get("files", {})
        return bool(files) and all(
            (root / relative).is_file()
            and hashlib.sha256((root / relative).read_bytes()).hexdigest() == digest
            for relative, digest in files.items()
        )
    except (OSError, ValueError, TypeError, AttributeError):
        return False


# 这些位置只验证模板开发工具，业务包自己的测试与运行安全检查不在其中。
def template_tool(path: Path, root: Path) -> bool:
    relative = path.relative_to(root / "server").as_posix()
    if relative.startswith("tests/architecture/"):
        return path.name != "test_structure.py"
    return relative == "tests/framework/test_commands.py"
