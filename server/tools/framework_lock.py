"""
框架文件摘要：记录框架代码、检查规则和工具的 SHA-256，保存在 server/framework.lock。
开发业务模块时不应改动这些文件；确实需要改框架时，审查后运行 --update 更新摘要，
并在提交说明中写明原因。这样每次框架改动都会在代码审查中清楚地出现。
它挡不住有意绕过的人，只保证改动不会悄悄发生。
pyproject.toml 只锁定 [tool] 下的检查与测试配置；依赖版本由 Dependabot 更新，更新时不需要改摘要。
"""

import argparse
import hashlib
import json
import sys
import tomllib
from pathlib import Path

from tools.quality.rules import ROOT

LOCK_FILE = ROOT / "framework.lock"
LOCKED = (
    "shared",
    "app/setup",
    "app/api/system",
    "app/api/errors.py",
    "app/api/identity.py",
    "app/api/middleware.py",
    "app/api/replies.py",
    "app/api/runner.py",
    "tools",
    "tests/framework",
    "tests/quality",
    "tests/architecture",
    "tests/conftest.py",
    "migrations/env.py",
    "migrations/script.py.mako",
    "pyproject.toml",
    "alembic.ini",
)
REGISTRATION = ("app/setup/catalog.py",)
SUFFIXES = (".py", ".md", ".mako", ".toml", ".ini", ".txt", ".html", ".js")


# pyproject.toml 中只取 [tool] 下的配置（ruff、mypy、pytest 等），依赖版本不参与摘要。
def tool_sections(content: bytes) -> bytes:
    tools = tomllib.loads(content.decode("utf-8")).get("tool", {})
    return json.dumps(tools, sort_keys=True, ensure_ascii=False).encode("utf-8")


PARTIAL = {"pyproject.toml": tool_sections}


# 计算全部框架文件的摘要。
def digests(root: Path = ROOT) -> dict[str, str]:
    found = {}
    for entry in LOCKED:
        base = root / entry
        paths = [base] if base.is_file() else sorted(base.rglob("*"))
        for path in paths:
            name = path.relative_to(root).as_posix()
            if (
                path.is_file()
                and path.suffix in SUFFIXES
                and "__pycache__" not in name
                and name not in REGISTRATION
            ):
                content = path.read_bytes()
                if name in PARTIAL:
                    content = PARTIAL[name](content)
                found[name] = hashlib.sha256(content).hexdigest()
    return found


# 列出与已记录摘要不同的文件。
def differences(root: Path = ROOT) -> list[str]:
    lock = root / LOCK_FILE.name
    if not lock.exists():
        return ["还没有 framework.lock，请运行 uv run python -m tools.framework_lock --update"]
    saved: dict[str, str] = json.loads(lock.read_text(encoding="utf-8"))
    current = digests(root)
    changes = [f"新增：{name}" for name in sorted(current.keys() - saved.keys())]
    changes += [f"删除：{name}" for name in sorted(saved.keys() - current.keys())]
    changes += [
        f"修改：{name}"
        for name in sorted(current.keys() & saved.keys())
        if current[name] != saved[name]
    ]
    return changes


# 检查或更新框架文件摘要。
def main() -> None:
    parser = argparse.ArgumentParser(description="检查或更新框架文件摘要")
    parser.add_argument("--update", action="store_true", help="审查过框架改动后，更新摘要")
    args = parser.parse_args()
    if args.update:
        LOCK_FILE.write_text(
            json.dumps(digests(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print("已更新 framework.lock；请在提交说明中写明这次框架改动的原因")
        return
    changes = differences()
    for line in changes:
        print(line)
    if changes:
        print("以上是框架文件的改动。确认是有意修改并已审查后，运行 --update。")
    sys.exit(1 if changes else 0)


if __name__ == "__main__":
    main()
