"""
登记再生成只合并明确业务绑定，不丢弃独立逻辑、系统路由或自定义接口属性。
"""

from pathlib import Path

import pytest
from fastapi_module.new_module import add_route
from fastapi_module.registry import registry_text
from fastapi_project.development.integration_registry import regenerate_catalog, regenerate_routers


# 两个实际模块目录与声明参与再生成，不从项目计划虚构可运行的包。
def package(project: Path, name: str) -> None:
    folder = project / "server/service" / name
    folder.mkdir(parents=True)
    (folder / "module.py").write_text("module = None\n")
    (folder / "module.json").write_text('{"module":"' + name + '"}')


# 分支分别加入一个模块的登记可以排序重建，旧列表无需人为拼接。
def test_catalog_rebuilds_from_real_package_declarations(tmp_path: Path) -> None:
    package(tmp_path, "sample_b")
    branch_b = registry_text(tmp_path / "server")
    package(tmp_path, "sample_a")
    result = regenerate_catalog(tmp_path, [branch_b])
    text = result.read_text()
    assert text.index("sample_a") < text.index("sample_b")
    assert text.count("module as sample_a") == 1
    with pytest.raises(ValueError, match="独立"):
        regenerate_catalog(tmp_path, [branch_b + "\nsetup_extra_feature()\n"])


# 两个新业务接口合并，系统接口和原实现的函数保持不变。
def test_router_rebuild_preserves_system_logic(tmp_path: Path) -> None:
    from fastapi_check.quality.rules import PROJECT

    original = (PROJECT / "server/app/api/routers.py").read_text()
    left = add_route(original, "sample_a")
    right = add_route(original, "sample_b")
    result = regenerate_routers(tmp_path, [left, right])
    text = result.read_text()
    assert "sample_a.router" in text and "sample_b.router" in text
    assert "health.router" in text and "def routers_for" in text
    assert "# 系统接口始终可用" in text
    with pytest.raises(ValueError, match="自定义"):
        regenerate_routers(
            tmp_path, [left.replace("sample_a.router", "sample_a.special_router"), right]
        )
    with pytest.raises(ValueError, match="系统"):
        regenerate_routers(tmp_path, [left.replace("health.router", "health.other_router"), right])
    with pytest.raises(ValueError, match="标准类型"):
        regenerate_routers(
            tmp_path,
            [left.replace("MODULE_ROUTERS: dict[str, tuple[APIRouter, ...]]", "MODULE_ROUTERS")],
        )


# 分支切换留下的纯缓存可忽略，实际未登记的Python或链接仍然报错。
def test_cache_only_deleted_package_is_not_business_code(tmp_path: Path) -> None:
    from shared.modules.layout import check_layout

    ghost = tmp_path / "service/sample_deleted/steps/__pycache__"
    ghost.mkdir(parents=True)
    (ghost / "old.pyc").write_bytes(b"synthetic-cache")
    assert not check_layout(tmp_path, [])
    source = ghost.parent / "actual.py"
    source.write_text("actual = True\n")
    assert check_layout(tmp_path, [])
    source.unlink()
    (ghost.parent / "linked.py").symlink_to(tmp_path / "missing.py")
    assert check_layout(tmp_path, [])
