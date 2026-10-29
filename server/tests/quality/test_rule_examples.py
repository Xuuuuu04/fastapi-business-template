"""
质量检查的反例：在临时目录中故意写出违规的代码和文档，确认每条检查都会报出。
防止检查本身失效却一直显示通过。
"""

from pathlib import Path
from typing import Any

from fastapi_check.quality.blocking import check_blocking
from fastapi_check.quality.docs import check_files as check_doc_files
from fastapi_check.quality.docs import check_rule_ids
from fastapi_check.quality.files import check_files
from fastapi_check.quality.naming import check_naming
from fastapi_check.quality.readmes import check_readmes
from fastapi_check.quality.registry import check_listed

from shared.modules.catalog import Catalog
from shared.modules.validation.imports import check_imports
from tests.framework.sample_modules import calc_module

GOOD_HEAD = '"""\n示例文件。\n"""\n\n'


# 在临时项目中写入一个文件。
def write(root: Path, name: str, text: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# 返回问题的规则名集合。
def rules_of(problems: list[Any]) -> set[str]:
    return {problem.rule for problem in problems}


# 缺少文件说明、类说明、函数说明，留了待办标记。
def test_comments_and_todo(tmp_path: Path) -> None:
    text = "class UserInput:\n    pass\n\ndef run_task():\n    return 1  # TODO 以后再改\n"
    write(tmp_path, "app/bad_file.py", text)
    assert {"file_header", "class_comment", "function_comment", "todo"} <= rules_of(
        check_files(tmp_path)
    )


# 类说明放在装饰器前或类内时均可接受，英文说明不能满足中文说明要求。
def test_class_explanations(tmp_path: Path) -> None:
    text = GOOD_HEAD + "# 用户输入。\n@dataclass\nclass UserInput:\n    pass\n\n"
    text += 'class UserResult:\n    """公开返回的用户信息。"""\n\n'
    write(tmp_path, "app/user_data.py", text)
    assert check_files(tmp_path) == []
    write(tmp_path, "app/user_data.py", GOOD_HEAD + 'class UserInput:\n    """Input."""\n')
    assert rules_of(check_files(tmp_path)) == {"class_comment"}


# 函数太长、嵌套太深、函数内连续注释太多、文件太长。
def test_lengths_and_nesting(tmp_path: Path) -> None:
    body = "".join(f"    total += {index}\n" for index in range(60))
    levels = ["for a in x:", "for b in a:", "if b:", "while b:", "if b:", "pass"]
    deep = "".join("    " * (depth + 1) + line + "\n" for depth, line in enumerate(levels))
    notes = "    # 第一行\n    # 第二行\n    # 第三行\n    pass\n"
    text = (
        GOOD_HEAD
        + "# 很长。\ndef long_one(total):\n"
        + body
        + "\n\n# 很深。\ndef deep_one(x):\n"
        + deep
    )
    text += "\n\n# 很多注释。\ndef noisy_one():\n" + notes + "\n" * 300
    write(tmp_path, "app/sample_code.py", text)
    assert {"function_lines", "nesting", "comment_run", "file_lines"} <= rules_of(
        check_files(tmp_path)
    )


# 文件名不是小写下划线、使用 utils、模块名只有一个词、步骤和条件名不合规。
def test_naming_rules(tmp_path: Path) -> None:
    write(tmp_path, "app/BadName.py", GOOD_HEAD)
    write(tmp_path, "app/utils.py", GOOD_HEAD)
    step_text = GOOD_HEAD + "# 步骤。\n@step('x')\ndef total(data):\n    pass\n\n\n"
    step_text += "# 条件。\n@condition('y')\ndef member(data):\n    pass\n"
    write(tmp_path, "service/notes/steps/work_items.py", step_text)
    rules = rules_of(check_naming(tmp_path))
    assert {"name_format", "name_vague", "module_name", "step_name", "condition_name"} <= rules


# 业务代码越过 shared.public、导入其他模块内部、步骤导入数据库库、框架导入业务、相对导入、动态导入。
def test_import_rules(tmp_path: Path) -> None:
    write(tmp_path, "service/order_desk/data.py", GOOD_HEAD + "from shared.flow.step import step\n")
    write(
        tmp_path,
        "service/order_desk/flow.py",
        GOOD_HEAD + "from service.stock_count.steps.x import y\n",
    )
    write(tmp_path, "service/order_desk/steps/read_rows.py", GOOD_HEAD + "import sqlalchemy\n")
    write(tmp_path, "shared/thing/work.py", GOOD_HEAD + "from app.setup import build\n")
    write(
        tmp_path, "app/api/v1/order_desk.py", GOOD_HEAD + "from service.order_desk.flow import x\n"
    )
    write(
        tmp_path,
        "service/order_desk/module.py",
        GOOD_HEAD + "from . import flow\nimport importlib\nimportlib.import_module('x')\n",
    )
    rules = rules_of(check_imports(tmp_path))
    expected = {
        "import_shared",
        "import_module",
        "import_database",
        "import_layer",
        "import_relative",
        "import_dynamic",
    }
    assert expected <= rules


# async 函数中调用 time.sleep。
def test_blocking_call(tmp_path: Path) -> None:
    write(
        tmp_path,
        "service/order_desk/steps/wait_rows.py",
        GOOD_HEAD + "import time\n\n\n# 等待。\nasync def wait_rows(data):\n    time.sleep(1)\n",
    )
    assert rules_of(check_blocking(tmp_path)) == {"blocking_call"}


# 目录缺少 README；模块 README 缺少固定小节和公开操作。
def test_readme_rules(tmp_path: Path) -> None:
    write(tmp_path, "app/sample_code.py", GOOD_HEAD)
    write(tmp_path, "service/order_desk/module.py", GOOD_HEAD)
    write(tmp_path, "service/order_desk/README.md", "# 订单台\n\n## 用途\n\n只写了用途。\n")
    rules = rules_of(check_readmes(tmp_path, {"order_desk": ["order_desk.create_order"]}))
    assert {"readme_missing", "readme_section", "readme_operation"} <= rules


# 缺少业务文档；代码引用的规则编号在 rules.md 中找不到。
def test_business_doc_rules(tmp_path: Path) -> None:
    folder = tmp_path / "doc" / "sample_calc"
    write(tmp_path, "doc/sample_calc/rules.md", "# 规则\n\n### R-01 会员优惠\n")
    assert rules_of(check_doc_files(folder, tmp_path)) == {"doc_missing"}
    problems = check_rule_ids(Catalog([calc_module]), "sample_calc", folder / "rules.md", tmp_path)
    assert [item.rule for item in problems] == ["rule_missing"] and "R-02" in problems[0].message


# service/ 下有模块没有登记到总目录；总目录登记的模块在 service/ 下找不到。
def test_unlisted_module(tmp_path: Path) -> None:
    write(tmp_path, "service/order_desk/module.py", GOOD_HEAD)
    problems = check_listed(Catalog([calc_module]), tmp_path)
    assert sorted(problem.rule for problem in problems) == ["missing_module", "not_listed"]
