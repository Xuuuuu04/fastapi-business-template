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
    "债务",
    "不能据此",
    "不代表",
    "不能说明",
    "不能代替",
    "——",
    "「",
    "」",
)
BANNED_PHRASES = ("Successful Response", "Validation Error")
STYLE_GENERATED = ("server/out/", "server/var/")


def writing_targets(project: Path) -> list[Path]:
    folders = [
        folder
        for folder in (
            project / ".agents" / "skills",
            project / "server",
            project / "design",
            project / "doc",
        )
        if folder.is_dir()
    ]
    singles = [
        project / "AGENTS.md",
        project / "README.md",
        project / "CONTRIBUTING.md",
        project / "SECURITY.md",
        project / "CODE_OF_CONDUCT.md",
        project / ".github" / "pull_request_template.md",
        project / "server" / "app" / "api" / "system" / "console.html",
        project / "server" / "app" / "api" / "system" / "console.js",
    ]
    return singles + [item for folder in folders for item in folder.rglob("*.md")]


def check_writing_style(project: Path = PROJECT) -> list[Problem]:
    problems: list[Problem] = []
    for path in writing_targets(project):
        if not path.exists():
            continue
        relative = path.relative_to(project).as_posix()
        if any(relative.startswith(prefix) for prefix in STYLE_GENERATED):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if path.suffix == ".js" and line.lstrip().startswith("//"):
                problems.append(
                    Problem(
                        relative,
                        number,
                        "no_comments",
                        "前端脚本中不要保留注释",
                        "删除 // 注释，用名字和结构表达意图",
                    )
                )
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
