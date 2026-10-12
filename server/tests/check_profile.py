"""
新产品保留框架集成检查；框架未改变时，模板工具自身的回归由模板仓库负责。
"""

import hashlib
import json
from pathlib import Path


# 只依据复制时的明确来源比较框架，不把本机检查历史或产品版本当成证明。
def product_framework_unchanged(root: Path) -> bool:
    path = root / "template-source.json"
    if not path.is_file():
        return False
    recorded = json.loads(path.read_text()).get("files", {})
    for relative, digest in recorded.items():
        source = root / relative
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            return False
    return bool(recorded)


# 这些位置只验证模板开发工具，业务包自己的测试与运行安全检查不在其中。
def template_tool(path: Path, root: Path) -> bool:
    relative = path.relative_to(root / "server").as_posix()
    if relative.startswith("tests/architecture/"):
        return path.name != "test_structure.py"
    return relative == "tests/framework/test_commands.py"
