import argparse
import hashlib
import json
import sys
import tomllib
from pathlib import Path

from shared.modules.validation.report import ROOT

LOCK_FILE = ROOT / "framework.lock"
LOCKED = (
    "devtools",
    "shared",
    "app/setup",
    "app/api/system",
    "app/api/errors.py",
    "app/api/identity.py",
    "app/api/identity_resolver.py",
    "app/api/middleware.py",
    "app/api/clock.py",
    "app/api/replies.py",
    "app/api/runner.py",
    "../.agents/skills",
    "tests/framework",
    "tests/quality",
    "tests/architecture",
    "tests/conftest.py",
    "tests/failure_reports.py",
    "tests/development_history.py",
    "tests/testing_app.py",
    "tests/resources.py",
    "tests/postgres_setup.py",
    "tests/environment.py",
    "tests/scheduling.py",
    "tests/template_project.py",
    "tests/check_profile.py",
    "migrations/env.py",
    "migrations/script.py.mako",
    "pyproject.toml",
    "alembic.ini",
)
REGISTRATION = ("app/setup/catalog.py",)
SUFFIXES = (".py", ".md", ".mako", ".toml", ".ini", ".txt", ".html", ".js", ".css", ".json")


def tool_sections(content: bytes) -> bytes:
    tools = tomllib.loads(content.decode("utf-8")).get("tool", {})
    return json.dumps(tools, sort_keys=True, ensure_ascii=False).encode("utf-8")


PARTIAL = {"pyproject.toml": tool_sections}


def digests(root: Path = ROOT) -> dict[str, str]:
    found = {}
    for entry in LOCKED:
        base = (root / entry).resolve()
        paths = [base] if base.is_file() else sorted(base.rglob("*"))
        for path in paths:
            name = (
                path.relative_to(root).as_posix()
                if path.is_relative_to(root)
                else "../" + path.relative_to(root.parent).as_posix()
            )
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


def differences(root: Path = ROOT, *, include_skills: bool = True) -> list[str]:
    lock = root / LOCK_FILE.name
    if not lock.exists():
        return ["还没有 framework.lock，请运行 uv run dev framework-lock --update"]
    saved: dict[str, str] = json.loads(lock.read_text(encoding="utf-8"))
    current = digests(root)
    if not include_skills:
        saved = {
            name: value
            for name, value in saved.items()
            if not name.startswith(("../", "devtools/"))
        }
        current = {
            name: value
            for name, value in current.items()
            if not name.startswith(("../", "devtools/"))
        }
    changes = [f"新增：{name}" for name in sorted(current.keys() - saved.keys())]
    changes += [f"删除：{name}" for name in sorted(saved.keys() - current.keys())]
    changes += [
        f"修改：{name}"
        for name in sorted(current.keys() & saved.keys())
        if current[name] != saved[name]
    ]
    return changes


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
