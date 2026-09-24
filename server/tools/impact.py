"""
改动影响报告：比较当前代码与基准分支，用中文列出这次改动影响了什么，供人观察和把关：
框架文件、涉及的模块、业务规则的增删改、待确认问题的变化、操作流程、接口、数据库迁移。
用法：uv run python -m tools.impact --base origin/main（在 server 目录运行）。
持续集成在合并请求上运行它，结果显示在检查的摘要页。只报告变化，不判断对错。
"""

import argparse
import json
import re
import subprocess
from collections.abc import Iterable
from pathlib import Path

from app.setup.catalog import MODULES
from tools.compare_api import compare
from tools.framework_lock import LOCKED
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
        output = self.git("diff", "--name-only", base)
        untracked = self.git("ls-files", "--others", "--exclude-standard")
        return sorted({line for line in (output + untracked).splitlines() if line})

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
    locked = [
        path
        for path in files
        if path.startswith("server/")
        and any(path[len("server/") :].startswith(entry) for entry in LOCKED)
    ]
    if not locked:
        return ["没有改动框架文件。"]
    return ["以下框架文件有改动，原因应写在提交说明中：", "", *[f"- `{path}`" for path in locked]]


# 涉及的模块：每个模块改动了代码、业务文档、接口还是测试。
def modules_part(files: list[str], modules: Iterable[str]) -> list[str]:
    rows = []
    for name in modules:
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


# 判断文件是否属于某个模块：路径中有以模块名命名的目录或文件。
def belongs(path: str, name: str) -> bool:
    parts = path.split("/")
    return name in parts[:-1] or parts[-1].split(".")[0] == name


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


# 生成完整报告。
def report(target: str, modules: Iterable[str], repo: Repo | None = None) -> str:
    repo = repo or Repo()
    base = repo.fork_point(target)
    files = repo.changed_files(base)
    parts = [
        ("框架文件", framework_part(files)),
        ("涉及的模块", modules_part(files, modules)),
        ("业务规则与待确认", rules_part(repo, base, files)),
        ("操作流程", flows_part(repo, base, files)),
        ("接口", api_part(repo, base)),
        ("数据库迁移", migrations_part(files)),
    ]
    lines = [f"# 改动影响（与 {target} 相比，共 {len(files)} 个文件）", ""]
    for title, body in parts:
        lines += [f"## {title}", "", *body, ""]
    return "\n".join(lines)


# 命令行入口。
def main() -> None:
    parser = argparse.ArgumentParser(description="列出与基准分支相比的改动影响")
    parser.add_argument("--base", default="origin/main", help="基准分支或提交，默认 origin/main")
    args = parser.parse_args()
    print(report(args.base, [module.name for module in MODULES]))


if __name__ == "__main__":
    main()
