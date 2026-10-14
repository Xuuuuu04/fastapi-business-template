"""
旧项目显式采用标准业务包结构。全部包检查通过后才写入 module.json，不改业务代码或登记表。
新开发包仍应通过 uv run dev new-module 创建。
"""

import json
import sys

from fastapi_check.quality.rules import ROOT

from app.setup.catalog import MODULES
from app.setup.structure import step_locations
from shared.modules.layout import check_layout, descriptor
from shared.modules.validation.imports import check_imports


# 不跳过违规，也不替旧代码猜位置；先修好结构再重试。
def main() -> None:
    problems = check_layout(ROOT, (module.name for module in MODULES), markers=False)
    problems += step_locations(MODULES)
    problems += [problem.text() for problem in check_imports(ROOT)]
    if problems:
        sys.exit("\n".join(problems))
    for module in MODULES:
        path = ROOT / "service" / module.name / "module.json"
        path.write_text(json.dumps(descriptor(module.name), indent=2) + "\n", encoding="utf-8")
    print("全部业务包已采用标准结构；业务规则、步骤与测试没有改动。请继续运行 uv run dev check。")


if __name__ == "__main__":
    main()
