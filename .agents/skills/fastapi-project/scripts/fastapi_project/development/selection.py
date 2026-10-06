"""
选择一轮检查的模块与文件：多包一次执行，修改前后的依赖共同决定受影响范围。
"""

import io
import json
import os
import subprocess
import sys
import tarfile
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi_check.quality.rules import PROJECT, ROOT
from fastapi_project.development.impact import impact_scope
from fastapi_project.development.versions import module_api_files

from shared.modules.catalog import Catalog


@dataclass(frozen=True)
class Selection:
    """本轮检查范围；空模块列表表示完整检查，而不是没有测试。"""

    modules: tuple[str, ...] = ()
    quick: bool = False
    reasons: tuple[str, ...] = ()
    unchanged: bool = False

    # 快速、单包、多包与完整检查分别留存，不把快速成功当成验收。
    def scope(self) -> dict[str, object]:
        if self.quick:
            return {"kind": "quick", "modules": list(self.modules)}
        if len(self.modules) == 1:
            return {"kind": "module", "module": self.modules[0]}
        if self.modules:
            return {"kind": "modules", "modules": list(self.modules)}
        return {"kind": "all"}


# 重复参数与逗号列表都支持，名称去重后排序，避免重复执行同一个包。
def module_names(values: list[str]) -> tuple[str, ...]:
    return tuple(
        sorted({name.strip() for value in values for name in value.split(",") if name.strip()})
    )


# 模块测试目录必须存在，避免错误路径造成未运行却认为检查成功。
def validate_modules(names: tuple[str, ...], catalog: Catalog, root: Path = ROOT) -> None:
    for name in names:
        if name not in catalog.modules:
            raise ValueError(f"模块没有登记：{name}")
        for group in ("modules", "integration"):
            if not list((root / "tests" / group / name).glob("test_*.py")):
                raise ValueError(f"模块缺少 tests/{group}/{name}/test_*.py")


# 文件存在性与后缀同时检查；Ruff 不接受已经删除的路径。
def module_files(names: tuple[str, ...], root: Path = ROOT) -> list[str]:
    files: set[Path] = set()
    for name in names:
        for folder in (
            root / "service" / name,
            root / "tests/modules" / name,
            root / "tests/integration" / name,
        ):
            files.update(folder.rglob("*.py"))
    ownership = module_api_files(root.parent)
    if ownership is None:
        files.update((root / "app/api/v1").rglob("*.py"))
    else:
        for name in names:
            files.update(ownership.get(name, []))
    return sorted(path.relative_to(root).as_posix() for path in files if path.is_file())


# Git 失败保留具体原因；没有可比较版本时不能假装没有改动。
def git(project: Path, *arguments: str) -> bytes:
    result = subprocess.run(["git", *arguments], cwd=project, capture_output=True, check=False)
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


# 基准快照只用于导入静态声明，不启动服务、不连接数据库、不复制虚拟环境。
def previous_graph(project: Path, revision: str) -> dict[str, list[str]]:
    archive = git(project, "archive", revision, "server")
    with TemporaryDirectory(prefix="check-dependencies-") as folder:
        with tarfile.open(fileobj=io.BytesIO(archive)) as source:
            source.extractall(folder, filter="data")
        code = (
            "import json; from app.setup.catalog import MODULES; from "
            "shared.modules.catalog import Catalog; "
            "print(json.dumps(Catalog(MODULES).links()))"
        )
        env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
        result = subprocess.run(
            [sys.executable, "-B", "-c", code],
            cwd=Path(folder) / "server",
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        if result.returncode:
            raise ValueError(f"旧版本依赖声明无法读取：{result.stderr.strip()}")
        links = json.loads(result.stdout)
        return {name: sorted(providers) for name, providers in links.items()}


# 新旧依赖取并集；删除一条调用后，原调用方仍要接受检查。
def affected_modules(direct: list[str], graphs: list[dict[str, list[str]]]) -> set[str]:
    reverse: dict[str, set[str]] = {}
    for graph in graphs:
        for caller, providers in graph.items():
            for provider in providers:
                reverse.setdefault(provider, set()).add(caller)
    found = set(direct)
    pending = deque(direct)
    while pending:
        for caller in sorted(reverse.get(pending.popleft(), set())):
            if caller not in found:
                found.add(caller)
                pending.append(caller)
    return found


# 公共或未知变化保持完整检查；旧图读取失败也扩大范围并明确说明。
def select_affected(catalog: Catalog, base: str, project: Path = PROJECT) -> Selection:
    revision = git(project, "merge-base", base, "HEAD").decode().strip()
    changed = git(project, "diff", "--name-only", "--no-renames", "-z", revision)
    changed += git(project, "ls-files", "--others", "--exclude-standard", "-z")
    paths = sorted({name for name in changed.decode().split("\0") if name})
    if not paths:
        return Selection(unchanged=True, reasons=("没有改动文件；本次未执行检查。",))
    scope = impact_scope(paths, catalog)
    if scope.full_check:
        return Selection(reasons=tuple(scope.full_check_reasons))
    if scope.unmapped:
        return Selection(
            reasons=(f"存在无法归属的改动，执行完整检查：{'、'.join(scope.unmapped)}",)
        )
    try:
        old = previous_graph(project, revision)
    except (
        ValueError,
        OSError,
        subprocess.TimeoutExpired,
        tarfile.TarError,
        json.JSONDecodeError,
    ) as error:
        return Selection(reasons=(f"无法安全缩小范围，执行完整检查：{error}",))
    current = {name: sorted(providers) for name, providers in catalog.links().items()}
    names = affected_modules(scope.direct, [old, current])
    if names - catalog.modules.keys():
        return Selection(reasons=("有已删除或未登记的受影响模块，执行完整检查。",))
    return Selection(
        tuple(sorted(names)), reasons=("按改动文件和修改前后的依赖，检查全部受影响包。",)
    )
