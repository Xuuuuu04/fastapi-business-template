"""
检查结论的整理：范围说明、失败原因和下一步命令，让读的人不用翻长输出。
"""

from typing import Any

from fastapi_check.matrix import CheckOptions
from fastapi_check.quality.rules import PROJECT

# 失败时给出的下一步，读的人不用回头翻长输出也知道该做什么。
NEXT_STEPS = {
    "迁移表归属": "请按上方列出的表补充归属登记",
    "代码风格": "请对上方列出的文件运行 uv run ruff check --fix，再处理剩余问题",
    "代码格式": "请对上方列出的文件运行 uv run ruff format",
    "类型检查": "请按上方 mypy 输出修正类型",
    "生成文档": "文档已过期，请运行 uv run dev docs",
}


# 产品框架没有改动时，说明哪些模板工具测试被省略；它们只在模板仓库里运行。
def announce_template_reuse(options: CheckOptions) -> None:
    from tests.check_profile import product_framework_unchanged

    if options.group == "framework":
        return
    if product_framework_unchanged(PROJECT):
        print(
            "框架未改动，沿用模板验证（省略模板工具测试，保留业务与框架运行安全测试）",
            flush=True,
        )


# 分组检查单独记范围，不能冒充同一范围的完整检查。
def check_scope(selection: Any, options: CheckOptions, modules: list[str]) -> dict[str, object]:
    if options.group == "all":
        return dict(selection.scope())
    return {"kind": "group", "group": options.group, "modules": modules}


# 测试失败时列出前几个失败的测试编号，完整情况在本轮记录里。
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
