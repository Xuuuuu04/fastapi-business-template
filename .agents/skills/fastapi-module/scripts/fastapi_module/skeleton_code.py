from fastapi_module.new_module import camel
from fastapi_module.skeleton_spec import SkeletonOperation, SkeletonPackage, call_field


def expression(reference: str) -> str:
    source, name = reference.rsplit(".", 1)
    return "data." + name if source == "input" else f"data.{call_field(source)}.{name}"


def work_field(reference: str) -> str:
    source, name = reference.rsplit(".", 1)
    return name if source == "input" else call_field(source)


def data_code(operation: SkeletonOperation, operations: dict[str, SkeletonOperation]) -> str:
    kind = camel(operation.name)
    imports = sorted({call.operation.split(".")[0] for call in operation.calls})
    code = "from shared.public import Data, WorkData, meaning\n"
    code += "".join(f"from service.{name} import public as {name}\n" for name in imports)
    for suffix, fields in (("Input", operation.input), ("Output", operation.output)):
        code += f"\n\nclass {kind}{suffix}(Data):\n"
        code += "".join(
            f"    {name}: {field.type} = meaning({field.meaning!r})\n"
            for name, field in fields.items()
        )
    code += f"\n\nclass {kind}Work(WorkData):\n"
    code += "".join(
        f"    {name}: {field.type} = meaning({field.meaning!r})\n"
        for name, field in operation.input.items()
    )
    for call in operation.calls:
        package, action = call.operation.split(".")
        text = operations[call.operation].title + "的结果"
        code += (
            f"    {call_field(call.operation)}: {package}.{camel(action)}Output "
            f"= meaning({text!r})\n"
        )
    code += f"    result: {kind}Output = meaning('最终结果')\n"
    return code


def public_code(package: SkeletonPackage) -> str:
    code = "from shared.public import contract\n"
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


def step_code(
    package: SkeletonPackage,
    operation: SkeletonOperation,
    operations: dict[str, SkeletonOperation],
) -> str:
    kind = camel(operation.name)
    code = f"from service.{package.name}.data_{operation.name} import {kind}Work, {kind}Output\n"
    code += "from shared.public import step" + (", Call" if operation.calls else "") + "\n"
    code += "".join(
        f"from service.{name} import public as {name}\n"
        for name in sorted({c.operation.split(".")[0] for c in operation.calls})
    )
    for call in operation.calls:
        package_name, action = call.operation.split(".")
        field, title = call_field(call.operation), operations[call.operation].title
        reads = sorted({work_field(reference) for reference in call.input.values()})
        values = ", ".join(
            f"{name}={expression(reference)}" for name, reference in call.input.items()
        )
        code += (
            f"\n\n@step({title!r}, reads={reads!r}, writes=[{field!r}], "
            f"uses=[{package_name}.{action}], observes=[{field!r}], simulated=False)\n"
            f"async def fetch_{field}(data: {kind}Work, call: Call) -> None:\n"
            f"    data.{field} = await call({package_name}.{action}, "
            f"{package_name}.{camel(action)}Input({values}))\n"
        )
    return code + result_step(operation)


def result_step(operation: SkeletonOperation) -> str:
    kind = camel(operation.name)
    if not operation.calls:
        reads = list(operation.input)
        return (
            f"\n\n@step({operation.title!r}, reads={reads!r}, writes=['result'], "
            f"observes={[*reads, 'result']!r}, simulated=True)\n"
            f"def build_result(data: {kind}Work) -> None:\n"
            "    raise NotImplementedError('此处尚未实现业务计算')\n"
        )
    reads = sorted({work_field(reference) for reference in operation.returns.values()})
    values = ", ".join(f"{name}={expression(ref)}" for name, ref in operation.returns.items())
    return (
        f"\n\n@step('整理最终结果', reads={reads!r}, writes=['result'], "
        "observes=['result'], simulated=False)\n"
        f"def build_result(data: {kind}Work) -> None:\n"
        f"    data.result = {kind}Output({values})\n"
    )


def flow_code(package: SkeletonPackage) -> str:
    code = "from shared.public import Flow\n"
    for operation in package.operations:
        code += (
            f"from service.{package.name}.data_{operation.name} "
            f"import {camel(operation.name)}Work\n"
        )
        code += f"from service.{package.name}.steps import build_{operation.name}\n"
    for operation in package.operations:
        steps = [f"build_{operation.name}.fetch_{call_field(c.operation)}" for c in operation.calls]
        steps += [f"build_{operation.name}.build_result"]
        code += (
            f"\n{operation.name}_flow = Flow({operation.title!r}, "
            f"work={camel(operation.name)}Work, "
            f"result='result', steps=[{', '.join(steps)}])\n"
        )
    return code


def module_code(package: SkeletonPackage) -> str:
    entries = ", ".join(f"public.{op.name}: flow.{op.name}_flow" for op in package.operations)
    return (
        f"from service.{package.name} import flow, public\nfrom shared.public import Module\n\n"
        f"module = Module({package.name!r}, {package.title!r}, '0.1.0', "
        f"{{{entries}}}, kind={package.kind!r})\n"
    )


def api_code(package: SkeletonPackage) -> str:
    code = (
        "from fastapi import APIRouter\nfrom app.api.runner import RunDep\n"
        f"from service.{package.name} import public\n\n"
        f"router = APIRouter(prefix='/api/v1/{package.name.replace('_', '-')}', "
        f"tags=[{package.title!r}])\n"
    )
    for operation in package.operations:
        kind = camel(operation.name)
        code += (
            f"\n\n@router.post('/{operation.name}', response_model=public.{kind}Output, "
            f"operation_id={package.name + '_' + operation.name!r}, summary={operation.title!r})\n"
            f"async def {operation.name}(body: public.{kind}Input, "
            f"run: RunDep) -> public.{kind}Output:\n"
            f"    return await run(public.{operation.name}, body)\n"
        )
    return code
