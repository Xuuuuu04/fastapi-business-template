import importlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi_check.quality.rules import PROJECT
from fastapi_template.template.initialization import initialize

from app.setup.catalog import MODULES as PROJECT_MODULES
from app.setup.structure import check_structure, step_locations
from shared.errors.framework import ConfigError
from shared.flow.flow import Flow
from shared.modules.layout import check_layout
from tests.architecture.sample_catalog import MODULES as SAMPLE_MODULES
from tests.testing_app import make_settings

MODULES = [*PROJECT_MODULES, *(replace(module, provides={}) for module in SAMPLE_MODULES)]


@pytest.fixture
def product(tmp_path: Path) -> Path:
    target = tmp_path / "product"
    initialize(PROJECT, target, "结构检查样例")
    for name, title in (("sample_records", "记录样例"), ("sample_accounts", "身份样例")):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "fastapi_dev.main",
                "new-module",
                name,
                "--title",
                title,
            ],
            cwd=target / "server",
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    return target / "server"


def test_existing_standard_modules(product: Path) -> None:
    check_structure(MODULES, product)
    assert check_layout(product, [module.name for module in MODULES]) == []


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


def test_missing_marker_requires_explicit_adoption(product: Path) -> None:
    marker = product / "service/sample_records/module.json"
    marker.unlink()
    with pytest.raises(ConfigError, match="uv run dev adopt-modules"):
        check_structure(MODULES, product)
    result = subprocess.run(
        [sys.executable, "-m", "fastapi_dev.main", "adopt-modules"],
        cwd=product,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(marker.read_text())["module"] == "sample_records"
    check_structure(MODULES, product)


def test_marker_cannot_expand_layout(product: Path) -> None:
    path = product / "service/sample_records/module.json"
    data = json.loads(path.read_text())
    data["allowed"] = ["helpers.py"]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ConfigError, match="结构说明"):
        check_structure(MODULES, product)


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


def test_default_build_stops_before_resources(
    product: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (product / "service/unknown_package").mkdir()
    setup = importlib.import_module("app.setup.build")
    monkeypatch.setattr(
        setup,
        "check_structure",
        lambda modules, **options: check_structure(modules, product, **options),
    )
    with pytest.raises(ConfigError, match="unknown_package"):
        setup.build(make_settings(tmp_path))


def test_computation_nodes_stay_in_steps() -> None:
    module = SAMPLE_MODULES[0]
    item, flow = next(iter(module.provides.items()))
    part = replace(flow.steps[0], func=test_computation_nodes_stay_in_steps)
    changed = Flow(
        flow.title, work=flow.work, result=flow.result, steps=(replace(part, when=None),)
    )
    problems = step_locations([replace(module, provides={item: changed})])
    assert len(problems) == 1 and "steps/" in problems[0]
