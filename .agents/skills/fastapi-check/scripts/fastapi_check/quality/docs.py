from pathlib import Path

from fastapi_check.quality.report import Problem
from fastapi_check.quality.rules import PROJECT

BANNED_WORDS = ("阻断", "巡检", "巡查", "红线", "门禁", "判官", "————", "「", "」")
BANNED_PHRASES = ("Successful Response", "Validation Error")
STYLE_SKIP = ("writing-style.md",)
STYLE_GENERATED = ("server/out/", "server/var/")


def check_writing_style(project: Path = PROJECT) -> list[Problem]:
    problems: list[Problem] = []
    folders = [project / ".agents" / "skills", project / "server"]
    singles = [project / "AGENTS.md", project / "README.md"]
    for path in singles + [item for folder in folders for item in folder.rglob("*.md")]:
        if not path.exists() or path.name in STYLE_SKIP:
            continue
        relative = path.relative_to(project).as_posix()
        if any(relative.startswith(prefix) for prefix in STYLE_GENERATED):
            continue
        if "/.agents/records/" in f"/{relative}":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for word in BANNED_WORDS + BANNED_PHRASES:
                if word in line:
                    problems.append(
                        Problem(
                            relative,
                            number,
                            "writing_style",
                            f"出现了禁用词 {word}",
                            "按文风与术语约定换成人能直接读懂的写法（fastapi-docs/references/writing-style.md）",
                        )
                    )
    return problems
