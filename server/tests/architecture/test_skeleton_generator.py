import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi_check.quality.rules import PROJECT
from fastapi_module.skeleton_spec import SkeletonBundle

from tests.architecture.test_operation_generators import COPY_FLAG, run, snapshot
from tests.environment import subprocess_environment
from tests.framework.skeleton_sample import implement, specification, write_inputs
from tests.template_project import initialize


@pytest.mark.parametrize("fault", ["future", "type", "effect", "access", "case", "field", "clash"])
def test_invalid_skeleton_mapping_rejected(fault: str) -> None:
    spec = specification()
    chain = spec["packages"][2]["operations"][0]
    if fault == "future":
        chain["calls"][0]["input"]["value"] = "sample_counts.advance.value"
    elif fault == "clash":
        chain["input"]["sample_sources_load"] = {"type": "int", "meaning": "与调用产出重名"}
    elif fault == "type":
        chain["input"]["value"]["type"] = "str"
    elif fault == "effect":
        spec["packages"][0]["operations"][0]["effect"] = "command"
    elif fault == "access":
        chain["access"] = "order.read"
    elif fault == "case":
        chain["cases"] = ["R-01-C01"]
    else:
        chain["input"]["value"]["type"] = "object"
    with pytest.raises(ValueError):
        SkeletonBundle.model_validate(spec).validate_links()


def test_old_phase_reference_lists_sources() -> None:
    spec = specification()
    spec["packages"][2]["operations"][0]["calls"][1]["input"]["value"] = "phase_1.value"
    with pytest.raises(ValueError, match="可用来源：input.字段、sample_sources.load.字段"):
        SkeletonBundle.model_validate(spec).validate_links()


def test_initialize_cases_and_atomic_validation(tmp_path: Path) -> None:
    from fastapi_module.skeleton import initialize_cases
    from fastapi_module.skeleton_files import validate_cases

    spec = tmp_path / "skeleton.json"
    spec.write_text(json.dumps(specification()))
    initialize_cases(tmp_path, spec)
    bundle = SkeletonBundle.model_validate(specification())
    for package in bundle.packages:
        validate_cases(tmp_path, package)
    case = tmp_path / "doc/sample_sources/cases/sample_sources.R-01-C01.json"
    original = case.read_text()
    case.write_text(original.replace("待填写", "独立填写"))
    initialize_cases(tmp_path, spec)
    assert "独立填写" in case.read_text()
    invalid = specification()
    invalid["packages"][0]["operations"][0]["access"] = "order.read"
    spec.write_text(json.dumps(invalid))
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="sample_sources.load.*权限"):
        initialize_cases(tmp_path, spec)
    assert snapshot(tmp_path) == before


def test_case_errors_show_identity_path_and_test(tmp_path: Path) -> None:
    from fastapi_module.skeleton_files import validate_cases

    package = SkeletonBundle.model_validate(specification()).packages[0]
    with pytest.raises(ValueError) as caught:
        validate_cases(tmp_path, package)
    message = str(caught.value)
    assert "sample_sources.R-01-C01" in message
    assert "doc/sample_sources/cases/*.json" in message
    assert "tests/modules/sample_sources/test_load.py::test_case" in message
    write_inputs(tmp_path)
    path = next((tmp_path / "doc/sample_sources/cases").glob("*.json"))
    case = json.loads(path.read_text())
    case["tests"] = ["tests/modules/sample_sources/wrong.py::test_case"]
    case["input"]["value"] = "错误类型"
    path.write_text(json.dumps(case))
    with pytest.raises(ValueError) as caught:
        validate_cases(tmp_path, package)
    assert "input.value 必须是 int" in str(caught.value)
    assert "tests/modules/sample_sources/test_load.py::test_case" in str(caught.value)


def verify_atomic_preview(copy: Path, spec: Path, entry: list[str], env: dict[str, str]) -> None:
    from fastapi_module.skeleton import generate

    bad = specification()
    bad["packages"][0]["operations"][0]["access"] = "order.read"
    spec.write_text(json.dumps(bad))
    before = snapshot(copy)
    with pytest.raises(ValueError, match="sample_sources.load.*权限"):
        generate(copy, spec)
    assert before == snapshot(copy)
    spec.write_text(json.dumps(specification()))
    before = snapshot(copy)
    preview = json.loads(run(copy, [*entry, "skeleton", "--spec", str(spec), "--preview"], env))
    assert preview["preview"] and before == snapshot(copy)


def verify_partial_implementation(copy: Path, entry: list[str], env: dict[str, str]) -> None:
    implement(copy, only="sample_counts")
    run(copy, ["-m", "ruff", "check", "service", "--fix"], env)
    run(copy, ["-m", "ruff", "format", "service"], env)
    run(copy, [*entry, "docs"], env)
    run(copy, [*entry, "check", "--module", "sample_counts", "--workers", "0"], env)
    delivery = subprocess.run(
        [
            sys.executable,
            *entry,
            "check",
            "--module",
            "sample_counts",
            "--delivery",
            "--workers",
            "0",
        ],
        cwd=copy / "server",
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert delivery.returncode != 0
    assert "交付不能包含模拟骨架" in delivery.stdout and "sample_sources.load" in delivery.stdout


@pytest.mark.sqlite_template
def test_three_package_skeleton_to_real_with_error_position(tmp_path: Path) -> None:
    if os.environ.get(COPY_FLAG):
        pytest.skip("模板副本不递归创建生成器验收")
    copy = tmp_path / "product"
    initialize(PROJECT, copy, "三包骨架验收")
    spec = copy / "skeleton-spec.json"
    spec.write_text(json.dumps(specification()))
    env = subprocess_environment() | {COPY_FLAG: "1"}
    entry = ["-c", "from fastapi_dev.main import main; main()"]
    run(copy, [*entry, "skeleton", "--init", "--spec", str(spec)], env)
    write_inputs(copy)
    verify_atomic_preview(copy, spec, entry, env)
    run(copy, [*entry, "skeleton", "--spec", str(spec)], env)
    service = "\n".join(path.read_text() for path in (copy / "server/service").rglob("*.py"))
    assert "992233" not in service and "496116" not in service
    tests = ["-m", "pytest", "-q", "tests/modules", "tests/integration/sample_chain"]
    run(copy, tests, env)
    verify_partial_implementation(copy, entry, env)
    implement(copy, wrong=True)
    import subprocess
    import sys

    failed = subprocess.run(
        [sys.executable, *tests],
        cwd=copy / "server",
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert failed.returncode != 0
    assert "最早不一致或未知位置" in failed.stdout and "sample_sources.load" in failed.stdout
    assert "实际" in failed.stdout and "期望" in failed.stdout and "build_load.py:" in failed.stdout
    implement(copy)
    run(copy, ["-m", "ruff", "check", "service", "--fix"], env)
    run(copy, ["-m", "ruff", "format", "service"], env)
    run(copy, [*entry, "docs"], env)
    run(copy, tests, env)
    run(copy, [*entry, "check", "--database", "sqlite", "--delivery", "--workers", "2"], env)
