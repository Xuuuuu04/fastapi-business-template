"""
质量检查的阈值、命名清单和例外登记。修改这里属于框架改动，需要单独审查。
阈值是试用值：用来提醒整理，不是为了让人把代码挤成一行或机械拆散。
"""

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT.parent

MAX_FILE_LINES = 300
MAX_FUNCTION_LINES = 50
MAX_NESTING = 4
MAX_COMMENT_RUN = 2
MAX_MODULE_README_LINES = 120
MAX_README_LINES = 150
MAX_BUSINESS_DOC_LINES = 200

CODE_DIRS = ("app", "service", "shared", "tools", "tests", "deploy")
README_DIRS = ("app", "service", "shared", "tools", "tests", "deploy", "migrations")
SKIP_PARTS = ("__pycache__", ".venv", "versions", "temp")

VAGUE_NAMES = frozenset(
    {
        "utils",
        "util",
        "common",
        "helper",
        "helpers",
        "misc",
        "manager",
        "managers",
        "stuff",
        "tmp",
        "lib",
        "core",
    }
)

STEP_VERBS = frozenset(
    {
        "read",
        "load",
        "find",
        "list",
        "count",
        "check",
        "clean",
        "merge",
        "build",
        "save",
        "create",
        "update",
        "delete",
        "remove",
        "send",
        "ask",
        "write",
        "mark",
        "pick",
        "sort",
        "group",
        "split",
        "fill",
        "match",
        "convert",
        "format",
        "expire",
        "sum",
        "fetch",
        "prepare",
        "apply",
        "publish",
        "record",
        "compare",
        "parse",
    }
)

CONDITION_WORDS = frozenset({"is", "has", "can", "needs", "should"})

MODULE_README_SECTIONS = (
    "## 用途",
    "## 公开操作",
    "## 依赖",
    "## 内部组织",
    "## 业务文档",
    "## 测试",
)

BUSINESS_DOCS = ("needs.md", "rules.md", "changes.md")

BLOCKING_CALLS = frozenset(
    {
        "time.sleep",
        "requests.get",
        "requests.post",
        "requests.put",
        "requests.delete",
        "requests.request",
        "urllib.request.urlopen",
        "urlopen",
        "sqlite3.connect",
        "psycopg.connect",
        "subprocess.run",
        "subprocess.call",
        "subprocess.check_output",
    }
)

TODO_WORDS = ("TODO", "FIXME", "XXX", "HACK")


# 明确允许的一项检查例外，注明文件、规则和原因。
@dataclass(frozen=True)
class Allowed:
    path: str
    rule: str
    reason: str


# 已审查的例外：写明文件、规则和原因。不再需要的例外会被检查报出。
ALLOWED: tuple[Allowed, ...] = ()
