import json
from pathlib import Path

from fastapi_module import skeleton_code as code
from fastapi_module.new_module import add_route
from fastapi_module.skeleton_spec import (
    CaseFixture,
    SkeletonBundle,
    SkeletonOperation,
    SkeletonPackage,
)
from fastapi_template.template.files import safe_path
from pydantic import TypeAdapter

from shared.scenarios.observations import ObservationPoint


def test_code(package: SkeletonPackage, operation: SkeletonOperation) -> str:
    dependencies = {call.operation: call.case for call in operation.calls}
    marks = ",\n".join(
        f"    pytest.param({case!r}, marks=pytest.mark.rule_case({case!r}))"
        for case in operation.cases
    )
    return (
        "from pathlib import Path\nimport pytest\n"
        "from tests.framework.skeleton_cases import run_case\n\n"
        f"@pytest.mark.anyio\n@pytest.mark.parametrize('identity', [\n{marks}\n])\n"
        "async def test_case(services, identity) -> None:\n"
        f"    actual, expected = await run_case(services, Path(__file__).resolve().parents[4], "
        f"{package.name + '.' + operation.name!r}, identity, {dependencies!r})\n"
        "    assert actual == expected\n"
    )


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
            package, operation, operations
        )
        files[root / "tests/modules" / package.name / ("test_" + operation.name + ".py")] = (
            test_code(package, operation)
        )
        names += [operation.name]
    files[folder / "data.py"] = (
        "".join(
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


def support_files(project: Path, package: SkeletonPackage) -> dict[Path, str]:
    folder = project / "server/service" / package.name
    files: dict[Path, str] = {}
    for name in ("contract", "sql", "tables"):
        files[folder / "store" / (name + ".py")] = ""
    return files


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
    catalog = "from shared.modules.module import Module\n" + "".join(
        f"from service.{name}.module import module as {name}\n" for name in names
    )
    files[root / "app/setup/catalog.py"] = (
        catalog + "\nMODULES: list[Module] = [" + ", ".join(names) + "]\n"
    )
    routers = (root / "app/api/routers.py").read_text()
    for package in sorted(bundle.packages, key=lambda pkg: pkg.name):
        routers = add_route(routers, package.name)
    files[root / "app/api/routers.py"] = routers
    for path, text in files.items():
        safe_path(project, path.relative_to(project).as_posix())
        if path.suffix == ".py":
            compile(text, str(path), "exec")
    return files


def read_cases(project: Path, folder: Path) -> tuple[list[CaseFixture], list[str]]:
    cases: list[CaseFixture] = []
    problems: list[str] = []
    for path in sorted(folder.glob("*.json")):
        try:
            source = safe_path(project, path.relative_to(project).as_posix())
            cases.append(CaseFixture.model_validate_json(source.read_bytes()))
        except ValueError as error:
            problems.append(f"{path.relative_to(project)}：{error}")
    return cases, problems


def metadata_problems(case: CaseFixture, test: str) -> list[str]:
    problems = []
    if case.initial or case.database or case.effects:
        problems.append(
            f"{case.id}：短骨架不支持 initial、database 或 effects，请编写独立真实状态测试"
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


def field_problems(case: CaseFixture, operation: SkeletonOperation) -> list[str]:
    problems = []
    types = {
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list[str]": list[str],
        "list[int]": list[int],
        "dict[str, str]": dict[str, str],
        "dict[str, int]": dict[str, int],
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


def interface_test(package: SkeletonPackage) -> str:
    paths = [f"/api/v1/{package.name.replace('_', '-')}/{op.name}" for op in package.operations]
    return (
        "def test_interfaces(client) -> None:\n"
        "    response = client.get('/openapi.json')\n    assert response.status_code == 200\n"
        f"    assert set({paths!r}) <= set(response.json()['paths'])\n"
    )
