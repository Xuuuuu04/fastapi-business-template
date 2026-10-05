"""
改动影响报告：比较当前代码与基准分支，用中文列出这次改动影响了什么，供人观察和把关：
框架文件、涉及的模块、业务规则的增删改、待确认问题的变化、操作流程、接口、数据库迁移。
用法：uv run python -m tools.impact --base origin/main（在 server 目录运行）。
当前由开发者手动运行，尚未加入持续集成。只报告变化，不判断对错。
"""

import argparse
import json
import re
import subprocess
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.setup.catalog import MODULES
from shared.config.settings import Settings
from shared.modules.catalog import Catalog
from tools.compare_api import compare
from tools.development.impact import (
    framework_files,
    impact_scope,
    module_area,
    scope_markdown,
)
from tools.progress_doc import PENDING, RULE_HEADING
from tools.quality.rules import PROJECT

OPERATION_HEADING = re.compile(r"^## .+（([\w.]+)）$")
TOP_HEADING = re.compile(r"^#{1,2} ")
AREAS = (
    ("server/service/", "代码"),
    ("doc/", "业务文档"),
    ("server/app/api/v1/", "接口"),
    ("server/tests/", "测试"),
)


# 读取指定 Git 版本的文件和差异，用于说明改动影响。
class Repo:
    # 在指定的仓库根目录读取 git 信息和文件，默认是本项目。
    def __init__(self, root: Path = PROJECT) -> None:
        self.root = root

    # 在仓库根目录执行 git 命令并返回输出。
    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=self.root, check=True, capture_output=True, text=True
        ).stdout

    # 列出与基准相比改动过的文件（相对仓库根目录），包括还没有提交的改动。
    def changed_files(self, base: str) -> list[str]:
        output = self.git("diff", "--name-only", "--no-renames", "-z", base)
        untracked = self.git("ls-files", "--others", "--exclude-standard", "-z")
        return sorted({path for path in (output + untracked).split("\0") if path})

    # 当前分支与基准分支的分叉点，只比较这个分支自己的改动。
    def fork_point(self, base: str) -> str:
        return self.git("merge-base", base, "HEAD").strip()

    # 读取基准版本中的文件内容；文件在基准中不存在时返回空文字。
    def base_text(self, base: str, path: str) -> str:
        try:
            return self.git("show", f"{base}:{path}")
        except subprocess.CalledProcessError:
            return ""

    # 读取当前工作区中的文件内容；文件已删除时返回空文字。
    def head_text(self, path: str) -> str:
        file = self.root / path
        return file.read_text(encoding="utf-8") if file.exists() else ""


# 按标题把文档切成段落，例如按规则编号或按操作名；遇到其他一、二级标题时段落结束。
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


# 比较两份段落，列出新增、删除和修改的标题；只差首尾空行不算修改。
def section_changes(before: dict[str, str], after: dict[str, str]) -> list[str]:
    lines = [f"新增 {key}" for key in after if key not in before]
    lines += [f"删除 {key}" for key in before if key not in after]
    changed = [key for key in after if key in before and before[key].strip() != after[key].strip()]
    lines += [f"修改 {key}" for key in changed]
    return lines


# 框架文件：受 framework.lock 保护的路径中改动过的文件。
def framework_part(files: list[str]) -> list[str]:
    locked = framework_files(files)
    if not locked:
        return ["没有改动框架文件。"]
    return ["以下框架文件有改动，原因应写在提交说明中：", "", *[f"- `{path}`" for path in locked]]


# 涉及的模块：每个模块改动了代码、业务文档、接口还是测试。
def modules_part(files: list[str], modules: Iterable[str]) -> list[str]:
    rows = []
    owners = {owner[0] for path in files if (owner := module_area(path))}
    for name in sorted(set(modules) | owners):
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


# 判断文件是否在模块的约定位置，避免内部同名目录误归属。
def belongs(path: str, name: str) -> bool:
    owner = module_area(path)
    return owner is not None and owner[0] == name


# 业务规则和待确认问题的变化。
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


# 操作流程的变化：生成的 flows.md 中哪些操作的章节变了。
def flows_part(repo: Repo, base: str, files: list[str]) -> list[str]:
    lines = []
    for path in files:
        if path.startswith("doc/") and path.endswith("/flows.md"):
            before = sections(repo.base_text(base, path), OPERATION_HEADING)
            after = sections(repo.head_text(path), OPERATION_HEADING)
            changes = section_changes(before, after)
            lines.append(f"- `{path}`：{'、'.join(changes) or '只改了数据模型或数据表'}")
    return lines or ["没有操作流程变化。"]


# 接口的变化：比较基准和当前的 doc/api/openapi.json。
def api_part(repo: Repo, base: str) -> list[str]:
    path = "doc/api/openapi.json"
    before = repo.base_text(base, path)
    if not before:
        return ["基准分支没有接口描述快照，这次无法比较。"]
    changes = compare(json.loads(before), json.loads(repo.head_text(path) or "{}"))
    return [f"- {line}" for line in changes] or ["接口没有变化。"]


# 数据库迁移：新增或改动的迁移文件。
def migrations_part(files: list[str]) -> list[str]:
    found = [path for path in files if path.startswith("server/migrations/versions/")]
    return [f"- `{path}`" for path in found] or ["没有数据库迁移。"]


# 机器报告保留原有各部分，并固定检查范围字段；所有内容来自同一份 Git 差异。
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


# Markdown 在原报告末尾追加检查范围，接口与迁移比较仍完整保留。
def markdown(data: dict[str, Any]) -> str:
    lines = [f"# 改动影响（与 {data['base']} 相比，共 {len(data['files'])} 个文件）", ""]
    for title, body in data["sections"].items():
        lines += [f"## {title}", "", *body, ""]
    return "\n".join(lines)


# 保留原调用入口；传入 Catalog 时也可用于独立模块声明测试。
def report(target: str, modules: Iterable[str] | Catalog, repo: Repo | None = None) -> str:
    catalog = modules if isinstance(modules, Catalog) else Catalog(MODULES)
    return markdown(report_data(target, catalog, repo))


# 命令行只读取启用配置用于展示；依赖图始终来自完整登记范围。
def main() -> None:
    parser = argparse.ArgumentParser(description="列出与基准分支相比的改动影响")
    parser.add_argument("--base", default="origin/main", help="基准分支或提交，默认 origin/main")
    parser.add_argument("--json", action="store_true", help="输出 schema_version=1 的稳定 JSON")
    args = parser.parse_args()
    data = report_data(args.base, Catalog(MODULES), disabled_modules=Settings().disabled_modules)
    print(json.dumps(data, ensure_ascii=False, indent=2) if args.json else markdown(data))


if __name__ == "__main__":
    main()
