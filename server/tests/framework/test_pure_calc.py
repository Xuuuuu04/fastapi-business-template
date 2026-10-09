"""
独立框架样例：包内反向依赖兼容、纯计算反例与声明图，无预置业务模块。
"""

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi_module import operation_templates
from fastapi_module.new_module import targets

from app.setup.structure import check_structure
from shared.errors.framework import ConfigError
from shared.flow.calculations import check_calculations
from shared.flow.flow import Flow
from shared.flow.step import step
from shared.graphs.observed import step_node
from shared.graphs.static import flow_graph
from shared.modules.catalog import Catalog
from shared.modules.module import Module
from shared.modules.validation.imports import check_imports
from shared.records.models import StepRecord
from tests.framework.sample_modules import calc_module


# 临时文件仅供源码结构检查，不登记到正式业务目录。
def source_file(root: Path, area: str, text: str) -> Path:
    path = root / "service/sample_calc" / area / "sample.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


# 旧反向导入警告，开关开启后报文件行号及改法。
@pytest.mark.parametrize("target", ["steps.sample", "data", "flow", "public", "module"])
def test_store_direction(tmp_path: Path, target: str) -> None:
    source_file(tmp_path, "store", f"from service.sample_calc.{target} import value\n")
    with pytest.warns(UserWarning, match="APP_MODULE_DEPENDENCIES_STRICT"):
        assert check_imports(tmp_path, strict=False) == []
    problem = check_imports(tmp_path, strict=True)[0]
    assert problem.path.endswith("store/sample.py") and problem.line == 1
    assert "calc/" in problem.hint
    with pytest.raises(ConfigError, match="import_direction"):
        check_structure([], tmp_path, strict=True)


# 新calc严格禁止数据库、时钟、随机、网络、文件和框架外部能力，包括别名。
@pytest.mark.parametrize(
    "code",
    [
        "from shared.public import Db\n",
        "import shared.public as public\npublic.Db()\n",
        "import sqlalchemy\n",
        "from datetime import datetime as clock\nclock.now()\n",
        "from datetime import date\ndate.today()\n",
        "from time import time\n",
        "import random\n",
        "import pathlib\n",
        "import httpx\n",
        'open("file")\n',
        'def compute(db):\n    return db.one("select 1")\n',
        "def compute(clock):\n    return clock.now()\n",
        "from service.sample_calc.store.contract import Store\n",
        "from service.other_calc.public import read\n",
    ],
)
def test_impure_calc(tmp_path: Path, code: str) -> None:
    source_file(tmp_path, "calc", code)
    problems = check_imports(tmp_path, strict=False)
    assert problems and all(problem.line > 0 for problem in problems)
    assert any("参数" in problem.hint for problem in problems)
    with pytest.raises(ConfigError):
        check_structure([], tmp_path, strict=False)


# 正常calc与store复用calc不需要数据库或业务运行夹具。
def test_normal_calc(tmp_path: Path) -> None:
    source_file(
        tmp_path, "calc", "from decimal import Decimal\ndef total(a, b):\n    return a + b\n"
    )
    source_file(tmp_path, "store", "from service.sample_calc.calc.sample import total\n")
    assert check_imports(tmp_path, strict=True) == []
    paths = targets("sample_calc")
    assert any(path.name == "test_calc.py" for path in paths.values())
    assert "services" not in operation_templates.calc_tests("sample_calc", "normalize")


# 独立函数模拟业务calc路径，声明检查无需安装业务模块。
def normalize(value: str) -> str:
    return value.strip()


normalize.__module__ = "service.sample_calc.calc.text"


# 步骤只有data参数，仍按原执行方式运行。
@step("整理", reads=["text"], writes=["text"], calcs=[normalize])
def build_text(data) -> None:
    data.text = normalize(data.text)


# 直接调用漏声明会报错，合法声明进入计算图与运行图。
def test_calc_declaration_and_graph() -> None:
    assert check_calculations(build_text, "sample_calc") == []
    assert "calcs" in check_calculations(replace(build_text, calcs=()), "sample_calc")[0]
    binding = next(iter(Catalog([calc_module]).bindings.values()))
    binding = replace(
        binding,
        flow=Flow(
            binding.flow.title,
            work=binding.flow.work,
            result=binding.flow.result,
            steps=[build_text],
        ),
    )
    assert "纯计算" in flow_graph(binding)
    record = StepRecord(
        "one",
        "build_text",
        "整理",
        "compute",
        "",
        "steps/text.py:1",
        calcs=["calc/text.py:1"],
        elapsed_ms=1.5,
    )
    assert "耗时计入本步骤" in step_node("one", 1, record)[0]
    record.calcs = None
    assert "未知（旧记录）" in step_node("one", 1, record)[0]


# 构建直接或经存储约定使用calc的独立声明，不登记到正式业务目录。
def runtime_module(through_store: bool) -> Module:
    from shared.data.models import Data, WorkData
    from shared.public import contract, meaning

    # 独立样例输入输出共用文本Data。
    class Text(Data):
        text: str = meaning("文本")

    # 纯计算操作的步骤数据，不需要数据库字段。
    class TextWork(WorkData):
        text: str = meaning("输入文本")
        result: Text = meaning("结果")

    # calc调用明确登记，执行器仍只计算所属步骤耗时。
    @step("整理文本", reads=["text"], writes=["result"], calcs=[normalize])
    def build_result(data: TextWork) -> None:
        data.result = Text(text=normalize(data.text))

    # 存储约定复用纯计算，仍在所属步骤声明，不另建业务模块。
    class TextStore:
        # 同步纯计算通过存储方法调用，不请求数据库。
        def clean(self, text: str) -> str:
            return normalize(text)

    # 经store调用的calc也进入声明图和所属步骤耗时。
    @step("整理文本", reads=["text"], writes=["result"], calcs=[normalize])
    def build_stored_result(data: TextWork, store: TextStore) -> None:
        data.result = Text(text=store.clean(data.text))

    operation = contract(
        "sample_calc.normalize", "纯计算样例", input=Text, output=Text, access="sample_calc.run"
    )
    flow = Flow(
        "计算",
        work=TextWork,
        result="result",
        steps=[build_stored_result if through_store else build_result],
    )
    return Module(
        "sample_calc",
        "独立纯计算样例",
        "1.0",
        {operation: flow},
        store=TextStore if through_store else None,
    )


# 同步纯函数单独测试无需数据库；运行链只额外验证框架记录与图。
@pytest.mark.anyio
@pytest.mark.parametrize("through_store", [False, True])
async def test_runtime_includes_calc_in_step(through_store: bool) -> None:
    from app.setup.build import build
    from shared.access.caller import SYSTEM
    from shared.config.settings import Settings
    from shared.records.stores import RunFilter

    module = runtime_module(through_store)
    operation = next(iter(module.provides))
    services = build(Settings(env="test", _env_file=None), modules=[module])
    try:
        result = await services.runtime.run(
            operation, operation.input(text=" 样例 "), caller=SYSTEM
        )
        assert result.text == "样例"
        records = await services.recorder.store.recent(RunFilter(), 1)
        assert records[0].steps[0].calcs and "normalize" in records[0].steps[0].calcs[0]
        assert records[0].steps[0].elapsed_ms >= 0
        assert "耗时计入本步骤" in step_node("one", 1, records[0].steps[0])[0]
    finally:
        await services.close()


# 新生成包默认严格；旧包结构说明仍合法且保持警告方式。
def test_new_package_strict(tmp_path: Path) -> None:
    path = source_file(tmp_path, "store", "from service.sample_calc.steps.sample import value\n")
    (path.parent.parent / "module.json").write_text('{"dependencies": "strict"}')
    assert check_imports(tmp_path, strict=False)[0].rule == "import_direction"
