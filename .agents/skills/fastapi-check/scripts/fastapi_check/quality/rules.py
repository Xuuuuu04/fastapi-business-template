from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6] / "server"
PROJECT = ROOT.parent

MAX_FILE_LINES = 300
MAX_FUNCTION_LINES = 50
MAX_NESTING = 4

CODE_DIRS = (
    "app",
    "service",
    "library",
    "shared",
    "../.agents/skills",
    "devtools",
    "tests",
)
BUSINESS_DIRS = ("service/", "library/", "app/api/v1/", "tests/modules/", "tests/integration/")
FRAMEWORK_TESTS = ("tests/integration/system/",)
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


@dataclass(frozen=True)
class Allowed:
    path: str
    rule: str
    reason: str


ALLOWED: tuple[Allowed, ...] = ()
