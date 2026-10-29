from typing import Any

from fastapi_check.matrix import CheckOptions
from fastapi_check.quality.rules import PROJECT

NEXT_STEPS = {
    "迁移表归属": "请按上方列出的表补充归属登记",
    "代码风格": "请对上方列出的文件运行 uv run ruff check --fix，再处理剩余问题",
    "代码格式": "请对上方列出的文件运行 uv run ruff format",
    "类型检查": "请按上方 mypy 输出修正类型",
    "生成文档": "文档已过期，请运行 uv run dev docs",
}


def announce_template_reuse(options: CheckOptions) -> None:
    from tests.check_profile import template_tools_unchanged

    if options.group == "framework":
        return
    if template_tools_unchanged(PROJECT):
        print(
            "模板工具未改动，沿用模板验证（省略模板工具测试，保留业务与框架运行安全测试）",
            flush=True,
        )


def check_scope(selection: Any, options: CheckOptions, modules: list[str]) -> dict[str, object]:
    if options.group == "all":
        return dict(selection.scope())
    return {"kind": "group", "group": options.group, "modules": modules}


def test_problems(title: str, evidence: dict[str, object]) -> list[str]:
    cases = evidence.get("cases")
    failed = [
        case["nodeid"]
        for case in (cases if isinstance(cases, list) else [])
        if isinstance(case, dict) and case.get("outcome") == "failed"
    ]
    if not failed:
        return [f"{title}：测试没有通过，请查看上方 pytest 输出"]
    extra = [f"{title}：另有 {len(failed) - 5} 个测试失败"] if len(failed) > 5 else []
    return [f"{title}：{name} 失败" for name in failed[:5]] + extra
