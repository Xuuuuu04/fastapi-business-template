"""
检查版本的组成规则：模块接口文件按归属参与本模块版本，总登记新增与无关模块的
接口修改不使旧模块的检查过期；公共变化与依赖失效仍使相关模块全部过期。
"""

from pathlib import Path

import pytest
from fastapi_check.quality.rules import PROJECT
from fastapi_project.development.history import fingerprints
from fastapi_project.development.versions import module_api_files

LINKS: dict[str, dict[str, list[str]]] = {"sample_records": {"sample_accounts": ["调用"]}}


# 写入文本并创建父目录，样例项目用它拼出需要的文件。
def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# 模块总目录的内容；names 顺序与真实文件一致，按登记顺序列出模块。
def catalog_text(names: list[str]) -> str:
    imports = "".join(f"from service.{name}.module import module as {name}\n" for name in names)
    entries = "".join(f"    {name},\n" for name in names)
    listing = f"MODULES: list[Module] = [\n{entries}]\n"
    return f"{imports}from shared.modules.module import Module\n\n{listing}"


# 路由登记的内容；mapping 是模块到接口文件名的归属，extra 是登记之外的公共代码。
def routers_text(mapping: dict[str, list[str]], extra: str = "") -> str:
    stems = sorted({stem for names in mapping.values() for stem in names} | {"stream"})
    entries = "".join(
        f'    "{name}": ({"".join(f"{stem}.router, " for stem in names)}),\n'
        for name, names in sorted(mapping.items())
    )
    return (
        '"""系统接口和业务接口的清单。"""\n'
        "from app.api.system import health\n"
        f"from app.api.v1 import {', '.join(stems)}\n\n"
        "ROUTERS = [health.router, stream.router]\n\n"
        f"MODULE_ROUTERS: dict[str, tuple] = {{\n{entries}}}\n\n"
        "def routers_for(modules):\n"
        "    return [*ROUTERS]\n" + extra
    )


# 与真实布局一致的样例项目：公共代码、两份总登记、系统与模块路由、两个业务模块。
def sample_project(root: Path) -> None:
    write(root / "server/shared/helper.py", "VALUE = 1\n")
    write(root / "server/app/setup/web.py", "def create_app():\n    return None\n")
    write(root / "server/app/setup/catalog.py", catalog_text(["sample_accounts", "sample_records"]))
    ownership = {
        "sample_accounts": ["sample_accounts", "sample_accounts_security"],
        "sample_records": ["sample_records"],
    }
    write(root / "server/app/api/routers.py", routers_text(ownership))
    write(root / "server/app/api/system/health.py", "router = None\n")
    for name in ("sample_accounts", "sample_records"):
        write(root / f"server/service/{name}/module.py", f"MODULE = '{name}'\n")
        write(root / f"server/tests/modules/{name}/test_flow.py", "def test_flow():\n    pass\n")
        write(root / f"server/app/api/v1/{name}.py", f"ROUTER = '{name}'\n")
    write(root / "server/app/api/v1/sample_accounts_security.py", "ROUTER = 'security'\n")
    write(root / "server/app/api/v1/stream.py", "ROUTER = 'stream'\n")


# 新增独立模块（总目录、路由登记、新代码与接口文件）不改变旧模块的检查版本。
def test_registering_new_module_keeps_old_versions(tmp_path: Path) -> None:
    sample_project(tmp_path)
    before = fingerprints(tmp_path, ["sample_accounts", "sample_records"], LINKS)
    write(tmp_path / "server/service/billing/module.py", "MODULE = 'billing'\n")
    write(tmp_path / "server/app/api/v1/billing.py", "ROUTER = 'billing'\n")
    write(
        tmp_path / "server/app/setup/catalog.py",
        catalog_text(["sample_accounts", "sample_records", "billing"]),
    )
    write(
        tmp_path / "server/app/api/routers.py",
        routers_text(
            {
                "sample_accounts": ["sample_accounts", "sample_accounts_security"],
                "sample_records": ["sample_records"],
                "billing": ["billing"],
            }
        ),
    )
    assert fingerprints(tmp_path, ["sample_accounts", "sample_records"], LINKS) == before


# 模块接口文件变化只影响归属模块与声明依赖它的调用方；无关模块不受影响。
def test_module_route_change_expires_owner_and_callers_only(tmp_path: Path) -> None:
    sample_project(tmp_path)
    write(tmp_path / "server/service/standalone/module.py", "MODULE = 'standalone'\n")
    names = ["sample_accounts", "sample_records", "standalone"]
    before = fingerprints(tmp_path, names, LINKS)
    write(tmp_path / "server/app/api/v1/sample_accounts.py", "ROUTER = 'sample_accounts-2'\n")
    changed = fingerprints(tmp_path, names, LINKS)
    assert changed["sample_accounts"] != before["sample_accounts"]
    assert changed["sample_records"] != before["sample_records"]
    assert changed["standalone"] == before["standalone"]
    write(tmp_path / "server/app/api/v1/sample_records.py", "ROUTER = 'files-2'\n")
    scoped = fingerprints(tmp_path, names, LINKS)
    assert scoped["sample_records"] != changed["sample_records"]
    assert scoped["standalone"] == changed["standalone"]


# 删除模块接口文件同样只影响归属模块与调用方。
def test_deleting_module_route_file_expires_owner_and_callers(tmp_path: Path) -> None:
    sample_project(tmp_path)
    write(tmp_path / "server/service/standalone/module.py", "MODULE = 'standalone'\n")
    names = ["sample_accounts", "sample_records", "standalone"]
    before = fingerprints(tmp_path, names, LINKS)
    (tmp_path / "server/app/api/v1/sample_accounts_security.py").unlink()
    changed = fingerprints(tmp_path, names, LINKS)
    assert changed["sample_accounts"] != before["sample_accounts"]
    assert changed["sample_records"] != before["sample_records"]
    assert changed["standalone"] == before["standalone"]


# 真实公共变化使全部模块过期；非模块路由（stream、系统接口）保守地算公共代码。
@pytest.mark.parametrize(
    ("path", "text"),
    [
        ("server/shared/helper.py", "VALUE = 2\n"),
        ("server/app/api/v1/stream.py", "ROUTER = 'stream-2'\n"),
        ("server/app/api/system/health.py", "router = 'health-2'\n"),
        ("server/app/setup/web.py", "def create_app():\n    return 'changed'\n"),
    ],
)
def test_shared_changes_expire_every_module(tmp_path: Path, path: str, text: str) -> None:
    sample_project(tmp_path)
    before = fingerprints(tmp_path, ["sample_accounts", "sample_records"], LINKS)
    write(tmp_path / path, text)
    assert fingerprints(tmp_path, ["sample_accounts", "sample_records"], LINKS) != before


# 没有归属的接口文件保守地算公共代码，新增也使全部模块过期。
def test_unrouted_api_file_counts_as_common(tmp_path: Path) -> None:
    sample_project(tmp_path)
    before = fingerprints(tmp_path, ["sample_accounts", "sample_records"], LINKS)
    write(tmp_path / "server/app/api/v1/orphan.py", "ROUTER = 'orphan'\n")
    assert fingerprints(tmp_path, ["sample_accounts", "sample_records"], LINKS) != before


# 登记文件里登记之外的部分（装配函数）仍是公共代码，变化使全部模块过期。
def test_registration_common_parts_still_expire_every_module(tmp_path: Path) -> None:
    sample_project(tmp_path)
    before = fingerprints(tmp_path, ["sample_accounts", "sample_records"], LINKS)
    ownership = {
        "sample_accounts": ["sample_accounts", "sample_accounts_security"],
        "sample_records": ["sample_records"],
    }
    write(
        tmp_path / "server/app/api/routers.py",
        routers_text(ownership, extra="def extra():\n    return 1\n"),
    )
    write(
        tmp_path / "server/app/setup/catalog.py",
        catalog_text(["sample_accounts", "sample_records"]) + "def helper():\n    return 1\n",
    )
    assert fingerprints(tmp_path, ["sample_accounts", "sample_records"], LINKS) != before


# 依赖目录内新增与删除文件都改变自身和调用方的版本；恢复原状后版本复原。
def test_dependency_file_changes_are_detected(tmp_path: Path) -> None:
    sample_project(tmp_path)
    before = fingerprints(tmp_path, ["sample_accounts", "sample_records"], LINKS)
    extra = tmp_path / "server/service/sample_accounts/extra.py"
    write(extra, "VALUE = 1\n")
    added = fingerprints(tmp_path, ["sample_accounts", "sample_records"], LINKS)
    assert added["sample_accounts"] != before["sample_accounts"]
    assert added["sample_records"] != before["sample_records"]
    extra.unlink()
    assert fingerprints(tmp_path, ["sample_accounts", "sample_records"], LINKS) == before
    (tmp_path / "server/service/sample_accounts/module.py").unlink()
    assert fingerprints(tmp_path, ["sample_accounts", "sample_records"], LINKS) != before


# 一轮版本计算里公共文件与被共享的依赖文件只读一次，不随模块数量重复。
def test_files_are_read_once_per_round(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sample_project(tmp_path)
    counts: dict[str, int] = {}
    original = Path.read_bytes

    # 统计每个文件名的读取次数，同时保留原始读取行为。
    def counting(path: Path) -> bytes:
        counts[path.name] = counts.get(path.name, 0) + 1
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", counting)
    fingerprints(tmp_path, ["sample_accounts", "sample_records"], LINKS)
    assert counts["helper.py"] == 1
    assert counts["module.py"] == 2
    assert counts["sample_accounts.py"] == 1


# 读不出静态归属或登记文件缺失时退回保守处理：接口文件全算公共，宁多失效不漏。
def test_unparsable_registration_keeps_everything_common(tmp_path: Path) -> None:
    sample_project(tmp_path)
    write(
        tmp_path / "server/app/api/routers.py",
        "from app.api.v1 import sample_records, sample_accounts\n\n"
        "def _routers():\n"
        '    return {"sample_accounts": (sample_accounts.router,)}\n\n'
        "MODULE_ROUTERS = _routers()\n",
    )
    before = fingerprints(tmp_path, ["sample_accounts", "sample_records"], LINKS)
    write(tmp_path / "server/app/api/v1/sample_records.py", "ROUTER = 'files-2'\n")
    after = fingerprints(tmp_path, ["sample_accounts", "sample_records"], LINKS)
    assert after != before
    (tmp_path / "server/app/api/routers.py").unlink()
    assert fingerprints(tmp_path, ["sample_accounts", "sample_records"], LINKS) != after


# 真实项目的接口归属与版本计算保持可用且确定。
def test_real_project_routes_and_versions() -> None:
    owned = module_api_files(PROJECT)
    from app.setup.catalog import MODULES

    assert owned is not None and set(owned) == {module.name for module in MODULES}


# 独立项目的主题接口归属和版本计算保持确定。
def test_sample_project_routes_and_versions(tmp_path: Path) -> None:
    sample_project(tmp_path)
    owned = module_api_files(tmp_path)
    assert owned is not None
    assert [path.name for path in owned["sample_records"]] == ["sample_records.py"]
    assert [path.name for path in owned["sample_accounts"]] == [
        "sample_accounts.py",
        "sample_accounts_security.py",
    ]
    codes = fingerprints(tmp_path, ["sample_accounts", "sample_records"])
    assert codes == fingerprints(tmp_path, ["sample_accounts", "sample_records"])
    assert codes["sample_accounts"] != codes["sample_records"]
