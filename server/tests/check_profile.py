"""
新产品保留框架集成检查；模板工具没有改动时，模板工具自身的回归由模板仓库负责。
"""

import hashlib
import json
from pathlib import Path


# 模板工具自己的文件：各 Skill 的脚本和 server/devtools；Skill 说明不算。
def template_tool_file(name: str) -> bool:
    return (name.startswith(".agents/skills/") and "/scripts/" in name) or name.startswith(
        "server/devtools/"
    )


# 只依据来源记录里模板工具文件的摘要比较；业务、依赖、迁移、框架运行代码和测试配置的改动不影响。
def template_tools_unchanged(root: Path) -> bool:
    path = root / "template-source.json"
    if not path.is_file():
        return False
    try:
        recorded = json.loads(path.read_text(encoding="utf-8")).get("files", {})
        tools = {name: digest for name, digest in recorded.items() if template_tool_file(name)}
        return bool(tools) and all(
            (root / relative).is_file()
            and hashlib.sha256((root / relative).read_bytes()).hexdigest() == digest
            for relative, digest in tools.items()
        )
    except (OSError, ValueError, TypeError, AttributeError):
        return False


# 这些位置只验证模板开发工具，业务包自己的测试与运行安全检查不在其中。
def template_tool(path: Path, root: Path) -> bool:
    relative = path.relative_to(root / "server").as_posix()
    if relative.startswith("tests/architecture/"):
        return path.name != "test_structure.py"
    return relative == "tests/framework/test_commands.py"
