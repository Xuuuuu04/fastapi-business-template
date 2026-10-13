"""
新包骨架的完整文件清单；已存在的业务包不覆盖，确认样例只作测试资料引用。
"""

import json
from pathlib import Path

from pydantic import TypeAdapter

from fastapi_module import skeleton_code as code
from fastapi_module.new_module import add_route
from fastapi_module.skeleton_spec import SkeletonBundle, SkeletonOperation, SkeletonPackage
from fastapi_project.development.confirmed_cases import CaseFixture
from fastapi_project.development.plan import check_plan, read_plan
from fastapi_template.template.files import safe_path

from shared.scenarios.observations import ObservationPoint


# 测试引用独立JSON，没有取值会写入服务代码；替换真实实现后继续跑相同样例。
def test_code(package: SkeletonPackage, operation: SkeletonOperation) -> str:
    dependencies = {call.operation: call.case for call in operation.calls}
    marks = ",\n".join(
        f"    pytest.param({case!r}, marks=pytest.mark.rule_case({case!r}))"
        for case in operation.cases
    )
    return (
        code.HEADER + "from pathlib import Path\nimport pytest\n"
        "from tests.framework.skeleton_cases import run_case\n\n"
        f"@pytest.mark.anyio\n@pytest.mark.parametrize('identity', [\n{marks}\n])\n"
        "# 同一份独立预期验证模拟与真实实现，模拟通过不代表可交付。\n"
        "async def test_case(services, identity) -> None:\n"
        f"    actual, expected = await run_case(services, Path(__file__).resolve().parents[4], "
        f"{package.name + '.' + operation.name!r}, identity, {dependencies!r})\n"
        "    assert actual == expected\n"
    )


# 标准目录一次生成，数据表与外部动作留给真实业务的独立实现和增量迁移。
def package_files(project: Path, package: SkeletonPackage, operations: dict) -> dict[Path, str]:
    root = project / "server"
    folder = root / "service" / package.name
    if folder.exists() or (root / "library" / package.name).exists():
        raise ValueError(f"{package.name}：业务包或同名工具已存在，不能覆盖 {folder}")
    files = {
        folder / "public.py": code.public_code(package),
        folder / "flow.py": code.flow_code(package),
        folder / "module.py": code.module_code(package),
        folder / "module.json": json.dumps(
            dict(
                schema_version=1,
                layout="standard",
                module=package.name,
                dependencies="strict",
                kind=package.kind,
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        folder / "steps/README.md": "# 业务步骤\n\n替换模拟计算，保持公开契约与独立确认样例。\n",
        folder / "store/README.md": "# 业务存储\n\n尚未使用数据库；新增表需独立增量迁移。\n",
        folder / "README.md": readme(package),
        root / "app/api/v1" / (package.name + ".py"): code.api_code(package),
        root / "tests/integration" / package.name / "test_interfaces.py": interface_test(package),
    }
    names = []
    for operation in package.operations:
        files[folder / ("data_" + operation.name + ".py")] = code.data_code(operation, operations)
        files[folder / "steps" / ("build_" + operation.name + ".py")] = code.step_code(
            package, operation
        )
        files[root / "tests/modules" / package.name / ("test_" + operation.name + ".py")] = (
            test_code(package, operation)
        )
        names += [operation.name]
    files[folder / "data.py"] = (
        code.HEADER
        + "".join(
            f"from service.{package.name}.data_{name} import "
            f"{code.camel(name)}Input, {code.camel(name)}Output, {code.camel(name)}Work\n"
            for name in names
        )
        + "\n__all__ = "
        + repr([code.camel(n) + suffix for n in names for suffix in ("Input", "Output", "Work")])
        + "\n"
    )
    files.update(support_files(project, package))
    return files


# 独立存储占位与业务文档只补缺失内容，不覆盖先写好的规则。
def support_files(project: Path, package: SkeletonPackage) -> dict[Path, str]:
    folder = project / "server/service" / package.name
    files: dict[Path, str] = {}
    for name in ("contract", "sql", "tables"):
        files[folder / "store" / (name + ".py")] = code.HEADER
    for name, text in (
        ("needs", "业务需求由产品独立填写，目前生成了声明骨架。"),
        ("rules", "规则与样例由产品独立提供，尚未确认的含义保持待确认。"),
        ("changes", "生成公开契约与模拟骨架，尚未完成真实业务实现。"),
    ):
        path = project / "doc" / package.name / (name + ".md")
        if not path.exists():
            files[path] = f"# {package.title}\n\n{text}\n"
    return files


# 规格全部检查完成再计算清单，预览不登记或写入任何业务。
def bundle_files(project: Path, bundle: SkeletonBundle) -> dict[Path, str]:
    bundle.validate_links()
    operations = {pkg.name + "." + op.name: op for pkg in bundle.packages for op in pkg.operations}
    files, problems = {}, []
    for package in bundle.packages:
        try:
            validate_cases(project, package)
        except ValueError as error:
            problems.append(str(error))
    if problems:
        raise ValueError("\n".join(problems))
    for package in bundle.packages:
        files.update(package_files(project, package, operations))
    root = project / "server"
    names = sorted(
        {path.parent.name for path in (root / "service").glob("*/module.json")}
        | {package.name for package in bundle.packages}
    )
    catalog = (
        code.HEADER
        + "from shared.modules.module import Module\n"
        + "".join(f"from service.{name}.module import module as {name}\n" for name in names)
    )
    files[root / "app/setup/catalog.py"] = (
        catalog + "\nMODULES: list[Module] = [" + ", ".join(names) + "]\n"
    )
    routers = (root / "app/api/routers.py").read_text()
    for package in sorted(bundle.packages, key=lambda pkg: pkg.name):
        routers = add_route(routers, package.name)
    files[root / "app/api/routers.py"] = routers
    index = (project / "doc/README.md").read_text()
    rows = "".join(
        f"| {pkg.name} | {pkg.title} | [需求]({pkg.name}/needs.md) · "
        f"[规则]({pkg.name}/rules.md) |\n"
        for pkg in bundle.packages
    )
    index = index.replace("| --- | --- | --- |\n", "| --- | --- | --- |\n" + rows, 1)
    files[project / "doc/README.md"] = index
    files[project / "project-plan.json"] = bundle_plan(project, bundle)
    for path, text in files.items():
        safe_path(project, path.relative_to(project).as_posix())
        if path.suffix == ".py":
            compile(text, str(path), "exec")
    return files


# 读取全部独立样例，保留每个文件的解析错误。
def read_cases(project: Path, folder: Path) -> tuple[list[CaseFixture], list[str]]:
    cases: list[CaseFixture] = []
    problems: list[str] = []
    for path in sorted(folder.glob("*.json")):
        try:
            cases.append(CaseFixture.model_validate_json(
                safe_path(project, path.relative_to(project).as_posix()).read_bytes()
            ))
        except ValueError as error:
            problems.append(f"{path.relative_to(project)}：{error}")
    return cases, problems


# 检查观察位置、状态初始化和测试引用，不修改用户资料。
def metadata_problems(case: CaseFixture, test: str) -> list[str]:
    problems = []
    if case.initial or case.database or case.effects:
        problems.append(
            f"{case.id}：短骨架不支持 initial、database 或 effects，"
            "请编写独立真实状态测试"
        )
    seen: set[ObservationPoint] = set()
    for observation in case.observations:
        try:
            if set(observation) != {"point", "value"}:
                raise ValueError("需要 point 和 value")
            point = ObservationPoint(**observation["point"])
            if point in seen:
                raise ValueError("观察位置重复")
            seen.add(point)
        except (ValueError, TypeError) as error:
            problems.append(f"{case.id}：observations 无效：{error}")
    if test not in case.tests:
        problems.append(f"{case.id}：期望 tests 包含 {test}")
    return problems


# 逐字段核对样例输入和预期类型，保留全部错误。
def field_problems(case: CaseFixture, operation: SkeletonOperation) -> list[str]:
    problems = []
    types = {        "str": str, "int": int, "float": float, "bool": bool,
        "list[str]": list[str], "list[int]": list[int],
        "dict[str, str]": dict[str, str], "dict[str, int]": dict[str, int],
    }
    for label, values, fields in (
        ("input", case.input, operation.input),
        ("expected", case.expected, operation.output),
    ):
        if set(values) != set(fields):
            problems.append(f"{case.id}：{label} 字段应为 {sorted(fields)}")
            continue
        for name, field in fields.items():
            try:
                TypeAdapter(types[field.type]).validate_python(values[name], strict=True)
            except ValueError:
                problems.append(f"{case.id}：{label}.{name} 必须是 {field.type}")
    return problems


# 确认样例必须已有，并准确引用即将生成的测试；不修改用户预期或引用。
def validate_cases(project: Path, package: SkeletonPackage) -> None:
    folder = project / "doc" / package.name / "cases"
    cases, problems = read_cases(project, folder)
    for operation in package.operations:
        for identity in operation.cases:
            matching = [case for case in cases if case.id == identity]
            test = f"tests/modules/{package.name}/test_{operation.name}.py::test_case"
            if len(matching) != 1:
                problems.append(
                    f"{identity}：找不到唯一样例；目录 {folder.relative_to(project)}/*.json；"
                    f"期望 tests 包含 {test}"
                )
                continue
            problems += metadata_problems(matching[0], test)
            problems += field_problems(matching[0], operation)
    if problems:
        raise ValueError("\n".join(problems))


# 固定README小节维持可读的结构，不用登记数量表达业务完成。
def readme(package: SkeletonPackage) -> str:
    return (
        f"# {package.title}\n\n## 用途\n\n从明确字段与连接声明生成，业务尚未实现。\n\n"
        "## 公开操作\n\n"
        + "\n".join(f"- {package.name}.{op.name}：{op.title}" for op in package.operations)
        + "\n\n## 依赖\n\n依赖来自各步骤公开调用，详细连接见flows.md。\n\n"
        "## 内部组织\n\ndata_主题.py定义数据，steps连接步骤，store保留真实存储位置。\n\n"
        f"## 业务文档\n\n见doc/{package.name}/。\n\n"
        "## 测试\n\n独立样例用于模拟及真实实现；交付拒绝尚未替换的模拟步骤。\n"
    )


# 接口目录检查实际OpenAPI路径，业务运算由模块及整链样例验证。
def interface_test(package: SkeletonPackage) -> str:
    paths = [f"/api/v1/{package.name.replace('_', '-')}/{op.name}" for op in package.operations]
    return (
        code.HEADER + "\n# 所有公开操作都已接到真实HTTP目录。\n"
        "def test_interfaces(client) -> None:\n"
        "    response = client.get('/openapi.json')\n    assert response.status_code == 200\n"
        f"    assert set({paths!r}) <= set(response.json()['paths'])\n"
    )


# 计划已有的节点保持预期范围，新声明必须符合已有包类型与操作计划。
def bundle_plan(project: Path, bundle: SkeletonBundle) -> str:
    plan = read_plan(project) or {"schema_version": 2, "name": project.name, "lines": []}
    plan["schema_version"] = 2
    existing = {pkg["module"]: pkg for line in plan["lines"] for pkg in line["packages"]}
    line = next((line for line in plan["lines"] if line["name"] == bundle.line), None)
    if line is None:
        line = {"name": bundle.line, "packages": []}
        plan["lines"].append(line)
    for package in bundle.packages:
        if package.name in existing:
            previous = existing[package.name]
            if previous.get("kind", "capability") != package.kind or not {
                op.name for op in package.operations
            } <= set(previous["operations"]):
                raise ValueError(f"{package.name}：骨架与已有计划的包类型或操作范围不一致，请先更新计划")
        else:
            line["packages"].append(
                {
                    "module": package.name,
                    "title": package.title,
                    "kind": package.kind,
                    "operations": [op.name for op in package.operations],
                    "dependencies": sorted(
                        {
                            call.operation.split(".")[0]
                            for op in package.operations
                            for call in op.calls
                        }
                    ),
                }
            )
    check_plan(plan)
    return json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
