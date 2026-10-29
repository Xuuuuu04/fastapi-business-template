from fastapi_module.new_module import camel


def data(name: str, module: str, state: str = "") -> tuple[str, str, str, str]:
    kind = camel(name)
    input, output, work, invalid = (
        kind + "Input",
        kind + "Output",
        kind + "Work",
        kind + "Invalid",
    )
    ready = '    ready: bool = meaning("等待状态", default=False)\n' if state else ""
    models = f'''
class {input}(Data):
    text: str = meaning("样例文本")


class {output}(Data):
    text: str = meaning("整理后的样例文本")


class {invalid}(BusinessError):
    code = "{module}_{name}_invalid"
    kind = Kind.INVALID
    message = "样例文本去空白后不能为空"


class {work}(WorkData):
    text: str = meaning("样例文本")
{ready}    result: {state or output} = meaning("操作结果")
'''
    return models, state or input, state or output, invalid


def step_code(module: str, name: str, output: str, invalid: str) -> str:
    kind = camel(name)
    return f"""from service.{module}.calc.{name} import normalize_text
from service.{module}.data import {kind}Work, {output}, {invalid}
from shared.public import step


@step("整理样例输入", reads=["text"], writes=["result"], calcs=[normalize_text])
def build_{name}(data: {kind}Work) -> None:
    value = normalize_text(data.text)
    if not value:
        raise {invalid}()
    data.result = {output}(text=value)
"""


def tests(module: str, name: str, input: str, invalid: str) -> str:
    return f"""import pytest
from service.{module} import public
from shared.access.caller import SYSTEM

pytestmark = pytest.mark.anyio


async def test_normal(operation_services) -> None:
    result = await operation_services.runtime.run(
        public.{name}, public.{input}(text=" 样例 "), caller=SYSTEM)
    assert result.text == "样例"


async def test_invalid(operation_services) -> None:
    with pytest.raises(public.{invalid}):
        await operation_services.runtime.run(public.{name}, public.{input}(text=" "), caller=SYSTEM)
"""


def fixture() -> str:
    return """import pytest


@pytest.fixture
async def operation_services(services):
    return services
"""


def calc_code() -> str:
    return """
def normalize_text(text: str) -> str:
    return text.strip()
"""


def calc_tests(module: str, name: str) -> str:
    return f"""from service.{module}.calc.{name} import normalize_text


def test_normalize_text() -> None:
    assert normalize_text(" 样例 ") == "样例"
    assert normalize_text(" ") == ""
"""
