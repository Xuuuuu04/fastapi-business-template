"""
新增操作的短骨架：明确的样例文本规则、一个成功和一个编号异常，共用运行夹具。
"""

from fastapi_module.new_module import camel


# 业务Data和错误各自命名，不和模块已有输入输出混用。
def data(name: str, module: str, rule: str, state: str = "") -> tuple[str, str, str, str]:
    kind = camel(name)
    input, output, work, invalid = (
        kind + "Input",
        kind + "Output",
        kind + "Work",
        kind + "Invalid",
    )
    ready = '    ready: bool = meaning("等待状态", default=False)\n' if state else ""
    models = f'''
# 生成样例输入，正式业务需替换为已确认Data。
class {input}(Data):
    text: str = meaning("样例文本")


# 生成样例输出，正式业务只返回声明的Data。
class {output}(Data):
    text: str = meaning("整理后的样例文本")


# 生成操作的规则异常。
class {invalid}(BusinessError):
    code = "{module}_{name}_invalid"
    kind = Kind.INVALID
    message = "样例文本去空白后不能为空"


# 操作步骤共享数据。
class {work}(WorkData):
    text: str = meaning("样例文本")
{ready}    result: {state or output} = meaning("操作结果")
'''
    return models, state or input, state or output, invalid


# 一个短步骤先跑通生成链，规则占位明确样例语义，业务实现留给开发包。
def step_code(module: str, name: str, rule: str, output: str, invalid: str) -> str:
    kind = camel(name)
    return f'''"""
生成操作的样例计算，业务迁移时按已确认规则替换。
"""

from service.{module}.data import {kind}Work, {output}, {invalid}
from shared.public import step


# 生成样例规则：去掉空白并拒绝空文本。
@step("整理样例输入", reads=["text"], writes=["result"], rule="{rule}")
def build_{name}(data: {kind}Work) -> None:
    value = data.text.strip()
    if not value:
        raise {invalid}()
    data.result = {output}(text=value)
'''


# 每个操作只生成两个样例，运行环境由目录公共夹具提供。
def tests(module: str, name: str, input: str, invalid: str, rule: str) -> str:
    return f'''"""
生成操作的正常及规则异常样例，业务数据由开发者按规则补充。
"""

import pytest
from service.{module} import public
from shared.access.caller import SYSTEM

pytestmark = pytest.mark.anyio


# 生成样例正常输入，证明公开登记和计算链可执行。
@pytest.mark.rule_case("{module}.{rule}-C01")
async def test_normal(operation_services) -> None:
    result = await operation_services.runtime.run(
        public.{name}, public.{input}(text=" 样例 "), caller=SYSTEM)
    assert result.text == "样例"


# 生成样例异常和规则编号相对应。
@pytest.mark.rule_case("{module}.{rule}-C02")
async def test_invalid(operation_services) -> None:
    with pytest.raises(public.{invalid}):
        await operation_services.runtime.run(public.{name}, public.{input}(text=" "), caller=SYSTEM)
'''


# 同模块所有新操作共用夹具，不在每个测试重复组装应用。
def fixture() -> str:
    return '''"""
新操作共用真实框架运行环境，数据库及配置使用项目统一测试夹具。
"""

import pytest


# 复用项目services，全部公开登记在同一测试环境执行。
@pytest.fixture
async def operation_services(services):
    return services
'''
