import argparse
import json
import re
import subprocess
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi_check.quality.rules import PROJECT
from fastapi_docs.progress_doc import PENDING, RULE_HEADING
from fastapi_migration.compare_api import compare
from fastapi_project.development.impact import (
    framework_files,
    impact_scope,
    module_area,
    scope_markdown,
)

from app.setup.application import application, application_modules
from shared.modules.catalog import Catalog

OPERATION_HEADING = re.compile(r"^## .+（([\w.]+)）$")
TOP_HEADING = re.compile(r"^#{1,2} ")
AREAS = (
    ("server/service/", "代码"),
    ("doc/", "业务文档"),
    ("server/app/api/v1/", "接口"),
    ("server/tests/", "测试"),
)


class Repo:
    def __init__(self, root: Path = PROJECT) -> None:
        self.root = root

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=self.root, check=True, capture_output=True, text=True
        ).stdout

    def changed_files(self, base: str) -> list[str]:
        output = self.git("diff", "--name-only", "--no-renames", "-z", base)
        untracked = self.git("ls-files", "--others", "--exclude-standard", "-z")
        return sorted({path for path in (output + untracked).split("\0") if path})

    def fork_point(self, base: str) -> str:
        return self.git("merge-base", base, "HEAD").strip()

    def base_text(self, base: str, path: str) -> str:
        try:
            return self.git("show", f"{base}:{path}")
        except subprocess.CalledProcessError:
            return ""

    def head_text(self, path: str) -> str:
        file = self.root / path
        return file.read_text(encoding="utf-8") if file.exists() else ""


def sections(text: str, heading: re.Pattern[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    current = ""
    for line in text.splitlines():
        match = heading.match(line)
        if match:
            current = match.group(1)
        elif TOP_HEADING.match(line):
            current = ""
        if current:
            found[current] = found.get(current, "") + line + "\n"
    return found


def section_changes(before: dict[str, str], after: dict[str, str]) -> list[str]:
    lines = [f"新增 {key}" for key in after if key not in before]
    lines += [f"删除 {key}" for key in before if key not in after]
    changed = [key for key in after if key in before and before[key].strip() != after[key].strip()]
    lines += [f"修改 {key}" for key in changed]
    return lines


def framework_part(files: list[str]) -> list[str]:
    locked = framework_files(files)
    if not locked:
        return ["没有改动框架文件。"]
    return ["以下框架文件有改动，原因应写在提交说明中：", "", *[f"- `{path}`" for path in locked]]


def modules_part(files: list[str], modules: Iterable[str]) -> list[str]:
    rows = []
    names = set(modules)
    owners = {owner[0] for path in files if (owner := module_area(path, names))}
    for name in sorted(names | owners):
        areas = [
            label
            for prefix, label in AREAS
            if any(path.startswith(prefix) and belongs(path, name) for path in files)
        ]
        if areas:
            rows.append(f"| {name} | {'、'.join(areas)} |")
    if not rows:
        return ["没有改动业务模块。"]
    return ["| 模块 | 改动 |", "| --- | --- |", *rows]


def belongs(path: str, name: str) -> bool:
    owner = module_area(path, [name])
    return owner is not None and owner[0] == name


def rules_part(repo: Repo, base: str, files: list[str]) -> list[str]:
    lines = []
    for path in files:
        if not path.endswith("/rules.md") or not path.startswith("doc/"):
            continue
        before, after = repo.base_text(base, path), repo.head_text(path)
        changes = section_changes(sections(before, RULE_HEADING), sections(after, RULE_HEADING))
        waiting = f"待确认 {before.count(PENDING)} → {after.count(PENDING)} 处"
        lines.append(f"- `{path}`：{'、'.join(changes) or '只改了规则以外的内容'}；{waiting}")
    return lines or ["没有改动业务规则。"]


def flows_part(repo: Repo, base: str, files: list[str]) -> list[str]:
    lines = []
    for path in files:
        if path.startswith("doc/") and path.endswith("/flows.md"):
            before = sections(repo.base_text(base, path), OPERATION_HEADING)
            after = sections(repo.head_text(path), OPERATION_HEADING)
            changes = section_changes(before, after)
            lines.append(f"- `{path}`：{'、'.join(changes) or '只改了数据模型或数据表'}")
    return lines or ["没有操作流程变化。"]


def api_part(repo: Repo, base: str) -> list[str]:
    path = "doc/api/openapi.json"
    before = repo.base_text(base, path)
    if not before:
        return ["基准分支没有接口描述快照，这次无法比较。"]
    changes = compare(json.loads(before), json.loads(repo.head_text(path) or "{}"))
    return [f"- {line}" for line in changes] or ["接口没有变化。"]


def migrations_part(files: list[str]) -> list[str]:
    found = [path for path in files if path.startswith("server/migrations/versions/")]
    return [f"- `{path}`" for path in found] or ["没有数据库迁移。"]


def report_data(
    target: str,
    catalog: Catalog,
    repo: Repo | None = None,
    disabled_modules: Iterable[str] = (),
) -> dict[str, Any]:
    repo = repo or Repo()
    base = repo.fork_point(target)
    files = repo.changed_files(base)
    scope = impact_scope(files, catalog, disabled_modules)
    parts = {
        "框架文件": framework_part(files),
        "涉及的模块": modules_part(files, catalog.modules),
        "业务规则与待确认": rules_part(repo, base, files),
        "操作流程": flows_part(repo, base, files),
        "接口": api_part(repo, base),
        "数据库迁移": migrations_part(files),
        "检查范围": scope_markdown(scope),
    }
    return {
        "schema_version": 1,
        "base": target,
        "fork_point": base,
        "files": files,
        **asdict(scope),
        "sections": parts,
    }


def markdown(data: dict[str, Any]) -> str:
    lines = [f"# 改动影响（与 {data['base']} 相比，共 {len(data['files'])} 个文件）", ""]
    for title, body in data["sections"].items():
        lines += [f"## {title}", "", *body, ""]
    return "\n".join(lines)


def report(target: str, modules: Iterable[str] | Catalog, repo: Repo | None = None) -> str:
    catalog = modules if isinstance(modules, Catalog) else Catalog(application_modules())
    return markdown(report_data(target, catalog, repo))


def main() -> None:
    parser = argparse.ArgumentParser(description="列出与基准分支相比的改动影响")
    parser.add_argument("--base", default="origin/main", help="基准分支或提交，默认 origin/main")
    parser.add_argument("--json", action="store_true", help="输出 schema_version=1 的稳定 JSON")
    parser.add_argument("--disabled-module", action="append", default=[], help="仅用于展示关闭状态")
    args = parser.parse_args()
    data = report_data(
        args.base,
        Catalog(application_modules()),
        disabled_modules=[
            *application().settings("offline").disabled_modules,
            *args.disabled_module,
        ],
    )
    print(json.dumps(data, ensure_ascii=False, indent=2) if args.json else markdown(data))


if __name__ == "__main__":
    main()
