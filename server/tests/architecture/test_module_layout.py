"""
标准业务包检查：脚本标记、文件位置、登记、依赖方向、计算节点和框架改动都由程序检查。
以真实模板副本模拟轻量 Agent 误建目录或越界修改；失败不得进入资源创建阶段。
"""

import importlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from app.setup.structure import check_structure, step_locations
from shared.errors.framework import ConfigError
from shared.flow.flow import Flow
from shared.modules.layout import check_layout
from tests.architecture.sample_catalog import MODULES as SAMPLE_MODULES
from tests.testing_app import make_settings
from tools.quality.rules import PROJECT
from tools.template.initialization import initialize

MODULES = [replace(module, provides={}) for module in SAMPLE_MODULES]


# 从真实模板生成独立产品，避免在工作目录里故意破坏源码。
@pytest.fixture
def product(tmp_path: Path) -> Path:
    target = tmp_path / "product"
    initialize(PROJECT, target, "结构检查样例")
    for name, title in (("sample_records", "记录样例"), ("sample_accounts", "身份样例")):
        result = subprocess.run(
            [sys.executable, "-m", "tools.new_module", name, "--title", title],
            cwd=target / "server",
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    return target / "server"


# 现有包和按用途拆分的数据、步骤与存储文件符合统一结构。
def test_existing_standard_modules(product: Path) -> None:
    check_structure(MODULES, product)
    assert check_layout(product, [module.name for module in MODULES]) == []


# 新文件不属于固定位置时拒绝，包括没有 module.py 的误建目录。
@pytest.mark.parametrize(
    "name",
    [
        "stray_module",
        "loose.py",
        "sample_records/helpers.py",
        "sample_records/steps/nested/broken.py",
        "sample_records/prompts/execute.py",
    ],
)
def test_unexpected_files_block_startup(product: Path, name: str) -> None:
    path = product / "service" / name
    if name == "stray_module":
        path.mkdir()
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# 错放的业务文件\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="标准"):
        check_structure(MODULES, product)


# 手工复制模块却遗漏生成说明时不能启动，旧包可显式采用结构再检查。
def test_missing_marker_requires_explicit_adoption(product: Path) -> None:
    marker = product / "service/sample_records/module.json"
    marker.unlink()
    with pytest.raises(ConfigError, match="tools.adopt_modules"):
        check_structure(MODULES, product)
    result = subprocess.run(
        [sys.executable, "-m", "tools.adopt_modules"], cwd=product, text=True, capture_output=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(marker.read_text())["module"] == "sample_records"
    check_structure(MODULES, product)


# 不能靠在说明文件里增加任意允许文件列表绕过固定结构。
def test_marker_cannot_expand_layout(product: Path) -> None:
    path = product / "service/sample_records/module.json"
    data = json.loads(path.read_text())
    data["allowed"] = ["helpers.py"]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ConfigError, match="结构说明"):
        check_structure(MODULES, product)


# 在业务包内越过 shared.public 或改受保护框架文件会拒绝启动。
@pytest.mark.parametrize(
    "name,text,reason",
    [
        (
            "service/sample_records/steps/store_records.py",
            "\nimport shared.flow.runtime\n",
            "import_shared",
        ),
        ("shared/flow/runner.py", "\n# 意外修改框架\n", "摘要"),
    ],
)
def test_dependency_and_framework_changes_block_startup(
    product: Path, name: str, text: str, reason: str
) -> None:
    path = product / name
    path.write_text(path.read_text() + text, encoding="utf-8")
    with pytest.raises(ConfigError, match=reason):
        check_structure(MODULES, product)


# 服务入口在创建数据库和外部资源前执行检查。
def test_default_build_stops_before_resources(
    product: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (product / "service/unknown_package").mkdir()
    setup = importlib.import_module("app.setup.build")
    monkeypatch.setattr(setup, "check_structure", lambda modules: check_structure(modules, product))
    with pytest.raises(ConfigError, match="unknown_package"):
        setup.build(make_settings(tmp_path))


# 已登记的流程也不能把计算函数搬到 flow.py 或任意辅助文件中。
def test_computation_nodes_stay_in_steps() -> None:
    module = SAMPLE_MODULES[0]
    item, flow = next(iter(module.provides.items()))
    part = replace(flow.steps[0], func=test_computation_nodes_stay_in_steps)
    changed = Flow(
        flow.title, work=flow.work, result=flow.result, steps=(replace(part, when=None),)
    )
    problems = step_locations([replace(module, provides={item: changed})])
    assert len(problems) == 1 and "steps/" in problems[0]
