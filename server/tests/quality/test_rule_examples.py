from pathlib import Path
from typing import Any

from fastapi_check.quality.blocking import check_blocking
from fastapi_check.quality.files import check_files
from fastapi_check.quality.naming import check_naming
from fastapi_check.quality.registry import check_listed

from shared.modules.catalog import Catalog
from shared.modules.validation.imports import check_imports
from tests.framework.sample_modules import calc_module


def write(root: Path, name: str, text: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def rules_of(problems: list[Any]) -> set[str]:
    return {problem.rule for problem in problems}


def test_comments_and_docstrings(tmp_path: Path) -> None:
    text = (
        '"""模块说明。"""\n\n\nclass UserInput:\n    """类说明。"""\n\n\n'
        'def run_task():\n    """函数说明。"""\n    return 1  # 行尾注释\n\n\n'
        '# 单独一行注释\nVALUE = "# 字符串里的井号不算注释"\n'
    )
    write(tmp_path, "app/bad_file.py", text)
    found = sorted((problem.rule, problem.line) for problem in check_files(tmp_path))
    assert found == [
        ("comment", 10),
        ("comment", 13),
        ("docstring", 1),
        ("docstring", 5),
        (
            "docstring",
            9,
        ),
    ]


def test_business_code_does_not_catch(tmp_path: Path) -> None:
    guarded = "def run():\n    try:\n        return 1\n    except ValueError:\n        return 0\n"
    silenced = (
        "import contextlib\n\n\ndef run():\n    with contextlib.suppress(KeyError):\n        pass\n"
    )
    write(tmp_path, "service/order_desk/steps/build_total.py", guarded)
    write(tmp_path, "app/api/v1/order_desk.py", silenced)
    write(tmp_path, "tests/integration/system/test_health.py", guarded)
    write(tmp_path, "shared/flow/runner.py", guarded)
    found = sorted((problem.path, problem.line) for problem in check_files(tmp_path))
    assert found == [
        ("app/api/v1/order_desk.py", 5),
        ("service/order_desk/steps/build_total.py", 2),
    ]


def test_plain_code_passes(tmp_path: Path) -> None:
    text = "@dataclass\nclass UserInput:\n    name: str\n\n\ndef run_task():\n    return 1\n"
    write(tmp_path, "app/user_data.py", text)
    assert check_files(tmp_path) == []


def test_lengths_and_nesting(tmp_path: Path) -> None:
    body = "".join(f"    total += {index}\n" for index in range(60))
    levels = ["for a in x:", "for b in a:", "if b:", "while b:", "if b:", "pass"]
    deep = "".join("    " * (depth + 1) + line + "\n" for depth, line in enumerate(levels))
    text = "def long_one(total):\n" + body + "\n\ndef deep_one(x):\n" + deep + "\n" * 300
    write(tmp_path, "app/sample_code.py", text)
    assert {"function_lines", "nesting", "file_lines"} <= rules_of(check_files(tmp_path))


def test_naming_rules(tmp_path: Path) -> None:
    write(tmp_path, "app/BadName.py", "")
    write(tmp_path, "app/utils.py", "")
    step_text = "@step('x')\ndef total(data):\n    pass\n\n\n"
    step_text += "@condition('y')\ndef member(data):\n    pass\n"
    write(tmp_path, "service/notes/steps/work_items.py", step_text)
    rules = rules_of(check_naming(tmp_path))
    assert {"name_format", "name_vague", "module_name", "step_name", "condition_name"} <= rules


def test_import_rules(tmp_path: Path) -> None:
    write(tmp_path, "service/order_desk/data.py", "from shared.flow.step import step\n")
    write(
        tmp_path,
        "service/order_desk/flow.py",
        "from service.stock_count.steps.x import y\n",
    )
    write(tmp_path, "service/order_desk/steps/read_rows.py", "import sqlalchemy\n")
    write(tmp_path, "shared/thing/work.py", "from app.setup import build\n")
    write(tmp_path, "app/api/v1/order_desk.py", "from service.order_desk.flow import x\n")
    write(
        tmp_path,
        "service/order_desk/module.py",
        "from . import flow\nimport importlib\nimportlib.import_module('x')\n",
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


def test_blocking_call(tmp_path: Path) -> None:
    write(
        tmp_path,
        "service/order_desk/steps/wait_rows.py",
        "import time\n\n\nasync def wait_rows(data):\n    time.sleep(1)\n",
    )
    assert rules_of(check_blocking(tmp_path)) == {"blocking_call"}


def test_unlisted_module(tmp_path: Path) -> None:
    write(tmp_path, "service/order_desk/module.py", "")
    problems = check_listed(Catalog([calc_module]), tmp_path)
    assert sorted(problem.rule for problem in problems) == ["missing_module", "not_listed"]
