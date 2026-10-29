from pathlib import Path

from fastapi_check.quality.report import Problem
from fastapi_check.quality.rules import PROJECT

BANNED_WORDS = (
    "阻断",
    "巡检",
    "巡查",
    "红线",
    "门禁",
    "判官",
    "夹具",
    "资产",
    "证据",
    "账本",
    "台账",
    "————",
    "「",
    "」",
)
BANNED_PHRASES = ("Successful Response", "Validation Error")
STYLE_GENERATED = ("server/out/", "server/var/")


def check_writing_style(project: Path = PROJECT) -> list[Problem]:
    problems: list[Problem] = []
    folders = [project / ".agents" / "skills", project / "server"]
    singles = [project / "AGENTS.md", project / "README.md"]
    for path in singles + [item for folder in folders for item in folder.rglob("*.md")]:
        if not path.exists():
            continue
        relative = path.relative_to(project).as_posix()
        if any(relative.startswith(prefix) for prefix in STYLE_GENERATED):
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
                            "换成人能直接读懂的大白话",
                        )
                    )
    return problems
