"""
从字段与连接声明生成代码，业务取值只由测试提供者给出，正式骨架保留明确的未实现标记。
"""

from fastapi_module.new_module import camel
from fastapi_module.skeleton_spec import SkeletonOperation, SkeletonPackage

HEADER = '"""\n显式声明生成的业务骨架；字段与连接属于契约，业务计算需独立实现。\n"""\n\n'


# 引用由规格检查过，只展开成字段访问，不执行任意表达式。
def expression(reference: str) -> str:
    source, name = reference.split(".")
    return "data." + name if source == "input" else f"data.{source}.{name}"


# 每个操作独立的数据文件，避免多操作的data.py不断变长。
def data_code(operation: SkeletonOperation, operations: dict[str, SkeletonOperation]) -> str:
    kind = camel(operation.name)
    imports = sorted({call.operation.split(".")[0] for call in operation.calls})
    code = HEADER + "from shared.public import Data, WorkData, meaning\n"
    code += "".join(f"from service.{name} import public as {name}\n" for name in imports)
    for suffix, fields in (("Input", operation.input), ("Output", operation.output)):
        code += (
            f"\n\n# 公开{suffix}字段由声明提供，不包含确认样例的取值。\n"
            f"class {kind}{suffix}(Data):\n"
        )
        code += "".join(
            f"    {name}: {field.type} = meaning({field.meaning!r})\n"
            for name, field in fields.items()
        )
    code += f"\n\n# 连接步骤只传递类型明确的中间产出。\nclass {kind}Work(WorkData):\n"
    code += "".join(
        f"    {name}: {field.type} = meaning({field.meaning!r})\n"
        for name, field in operation.input.items()
    )
    for number, call in enumerate(operation.calls, 1):
        package, action = call.operation.split(".")
        code += (
            f"    phase_{number}: {package}.{camel(action)}Output = meaning('第{number}阶段产出')\n"
        )
    code += f"    result: {kind}Output = meaning('最终结果')\n"
    return code


# 公共入口只公开契约和输入输出类，不导出流程或步骤。
def public_code(package: SkeletonPackage) -> str:
    code = HEADER + "from shared.public import contract\n"
    exports = []
    for operation in package.operations:
        kind = camel(operation.name)
        code += (
            f"from service.{package.name}.data_{operation.name} import {kind}Input, {kind}Output\n"
        )
        exports += [operation.name, kind + "Input", kind + "Output"]
    for operation in package.operations:
        kind = camel(operation.name)
        code += (
            f"\n{operation.name} = contract({package.name + '.' + operation.name!r}, "
            f"{operation.title!r}, input={kind}Input, output={kind}Output, "
            f"access={operation.access!r}, effect={operation.effect!r})\n"
        )
    return code + f"\n__all__ = {exports!r}\n"


# 用明确映射连接每一阶段，最终整理结果是实际连接逻辑，不编造业务计算。
def step_code(package: SkeletonPackage, operation: SkeletonOperation) -> str:
    kind = camel(operation.name)
    code = (
        HEADER
        + f"from service.{package.name}.data_{operation.name} import {kind}Work, {kind}Output\n"
    )
    code += "from shared.public import step" + (", Call" if operation.calls else "") + "\n"
    code += "".join(
        f"from service.{name} import public as {name}\n"
        for name in sorted({c.operation.split(".")[0] for c in operation.calls})
    )
    for number, call in enumerate(operation.calls, 1):
        package_name, action = call.operation.split(".")
        reads = sorted(
            {
                ref.split(".")[1] if ref.startswith("input.") else ref.split(".")[0]
                for ref in call.input.values()
            }
        )
        values = ", ".join(
            f"{name}={expression(reference)}" for name, reference in call.input.items()
        )
        code += (
            f"\n\n# 调用声明过的第{number}阶段，入参来源明确。\n"
            f"@step('调用第{number}阶段', reads={reads!r}, writes=['phase_{number}'], "
            f"uses=[{package_name}.{action}], observes=['phase_{number}'], simulated=False)\n"
            f"async def call_phase_{number}(data: {kind}Work, call: Call) -> None:\n"
            f"    data.phase_{number} = await call({package_name}.{action}, "
            f"{package_name}.{camel(action)}Input({values}))\n"
        )
    return code + result_step(operation)


# 没有业务计算的地方只留下模拟标记，不把expected值写入生产函数。
def result_step(operation: SkeletonOperation) -> str:
    kind = camel(operation.name)
    if not operation.calls:
        reads = list(operation.input)
        return (
            "\n\n# 模拟提供者只在测试上下文注入，正式业务需要替换此步骤。\n"
            f"@step({operation.title!r}, reads={reads!r}, writes=['result'], "
            f"observes={[*reads, 'result']!r}, simulated=True)\n"
            f"def build_result(data: {kind}Work) -> None:\n"
            "    raise NotImplementedError('此处尚未实现业务计算')\n"
        )
    reads = sorted(
        {
            ref.split(".")[1] if ref.startswith("input.") else ref.split(".")[0]
            for ref in operation.returns.values()
        }
    )
    values = ", ".join(f"{name}={expression(ref)}" for name, ref in operation.returns.items())
    return (
        "\n\n# 按显式字段映射整理最终结果。\n"
        f"@step('整理最终结果', reads={reads!r}, writes=['result'], "
        "observes=['result'], simulated=False)\n"
        f"def build_result(data: {kind}Work) -> None:\n"
        f"    data.result = {kind}Output({values})\n"
    )


# 每个操作连到自己明确的步骤序列，不从预期猜数据流。
def flow_code(package: SkeletonPackage) -> str:
    code = HEADER + "from shared.public import Flow\n"
    for operation in package.operations:
        code += (
            f"from service.{package.name}.data_{operation.name} "
            f"import {camel(operation.name)}Work\n"
        )
        code += f"from service.{package.name}.steps import build_{operation.name}\n"
    for operation in package.operations:
        steps = [
            f"build_{operation.name}.call_phase_{i}" for i in range(1, len(operation.calls) + 1)
        ]
        steps += [f"build_{operation.name}.build_result"]
        code += (
            f"\n{operation.name}_flow = Flow({operation.title!r}, "
            f"work={camel(operation.name)}Work, "
            f"result='result', steps=[{', '.join(steps)}])\n"
        )
    return code


# 骨架不生成数据库表或对外效果，后续真实实现单独提供增量迁移。
def module_code(package: SkeletonPackage) -> str:
    entries = ", ".join(f"public.{op.name}: flow.{op.name}_flow" for op in package.operations)
    return (
        HEADER
        + f"from service.{package.name} import flow, public\nfrom shared.public import Module\n\n"
        f"module = Module({package.name!r}, {package.title!r}, '0.1.0', "
        f"{{{entries}}}, kind={package.kind!r})\n"
    )


# HTTP入口只做类型转换，权限和业务行为继续由公开操作决定。
def api_code(package: SkeletonPackage) -> str:
    code = HEADER + (
        "from fastapi import APIRouter\nfrom app.api.runner import RunDep\n"
        f"from service.{package.name} import public\n\n"
        f"router = APIRouter(prefix='/api/v1/{package.name.replace('_', '-')}', "
        f"tags=[{package.title!r}])\n"
    )
    for operation in package.operations:
        kind = camel(operation.name)
        code += (
            f"\n\n# 调用{operation.title}的公开操作。\n"
            f"@router.post('/{operation.name}', response_model=public.{kind}Output, "
            f"operation_id={package.name + '_' + operation.name!r}, summary={operation.title!r})\n"
            f"async def {operation.name}(body: public.{kind}Input, "
            f"run: RunDep) -> public.{kind}Output:\n"
            f"    return await run(public.{operation.name}, body)\n"
        )
    return code
