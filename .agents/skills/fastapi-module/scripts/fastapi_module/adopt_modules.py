import json
import sys

from fastapi_check.quality.rules import ROOT

from app.setup.catalog import MODULES
from app.setup.structure import step_locations
from shared.modules.layout import check_layout, descriptor
from shared.modules.validation.imports import check_imports


def main() -> None:
    problems = check_layout(ROOT, (module.name for module in MODULES), markers=False)
    problems += step_locations(MODULES)
    problems += [problem.text() for problem in check_imports(ROOT)]
    problems += [
        f'service/{module.name}/module.py：Module 要写 kind="capability" 或 kind="workflow"'
        for module in MODULES
        if module.kind is None
    ]
    if problems:
        sys.exit("\n".join(problems))
    for module in MODULES:
        path = ROOT / "service" / module.name / "module.json"
        marker = descriptor(module.name, kind=module.kind or "")
        path.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    print("全部业务包已采用标准结构；业务规则、步骤与测试没有改动。请继续运行 uv run dev check。")


if __name__ == "__main__":
    main()
