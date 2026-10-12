"""
实际副本三包骨架、模拟到实现与首个中间差异验收；只运行隔离的生成项目。
"""

import json
import os
from pathlib import Path

import pytest
from fastapi_check.quality.rules import PROJECT
from fastapi_module.skeleton_spec import SkeletonBundle
from fastapi_template.template.initialization import initialize

from tests.architecture.test_operation_generators import COPY_FLAG, run, snapshot
from tests.environment import subprocess_environment
from tests.framework.skeleton_sample import implement, specification, write_inputs


# 错误连接在写文件之前拒绝，未来字段、类型差异和查询写入都不能猜着接。
@pytest.mark.parametrize("fault", ["future", "type", "effect"])
def test_invalid_skeleton_mapping_rejected(fault: str) -> None:
    spec = specification()
    chain = spec["packages"][2]["operations"][0]
    if fault == "future":
        chain["calls"][0]["input"]["value"] = "phase_2.value"
    elif fault == "type":
        chain["input"]["value"]["type"] = "str"
    else:
        spec["packages"][0]["operations"][0]["effect"] = "command"
    with pytest.raises(ValueError):
        SkeletonBundle.model_validate(spec).validate_links()


# 相同独立资料先验证模拟连接，再替换实际计算，故意错误会指出最早观察到的字段。
@pytest.mark.sqlite_template
def test_three_package_skeleton_to_real_with_error_position(tmp_path: Path) -> None:
    if os.environ.get(COPY_FLAG):
        pytest.skip("模板副本不递归创建生成器验收")
    copy = tmp_path / "product"
    initialize(PROJECT, copy, "三包骨架验收")
    spec = write_inputs(copy)
    env = subprocess_environment() | {COPY_FLAG: "1"}
    entry = ["-c", "from fastapi_dev.main import main; main()"]
    before = snapshot(copy)
    preview = json.loads(run(copy, [*entry, "skeleton", "--spec", str(spec), "--preview"], env))
    assert preview["preview"] and before == snapshot(copy)
    run(copy, [*entry, "skeleton", "--spec", str(spec)], env)
    service = "\n".join(path.read_text() for path in (copy / "server/service").rglob("*.py"))
    assert "992233" not in service and "496116" not in service
    tests = ["-m", "pytest", "-q", "tests/modules", "tests/integration/sample_chain"]
    run(copy, tests, env)
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
    implement(copy)
    run(copy, ["-m", "ruff", "check", "service", "--fix"], env)
    run(copy, ["-m", "ruff", "format", "service"], env)
    run(copy, [*entry, "docs"], env)
    run(copy, tests, env)
