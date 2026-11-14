import json
import shutil
from pathlib import Path

from fastapi_template.template.files import provenance, safe_path, save_provenance

ENTRIES = (
    ".agents/skills",
    ".github",
    ".gitignore",
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    "CHANGELOG.md",
    "server",
    "doc",
)
IGNORED = (
    ".git",
    ".agents",
    ".agent",
    ".env",
    ".venv",
    "__pycache__",
    "*.pyc",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "var",
    "out",
    "template-source.json",
    "ISSUE_TEMPLATE",
)


def check_source(source: Path) -> None:
    for entry in ENTRIES:
        path = safe_path(source, entry)
        if path.is_dir():
            check_folder(path)


def check_folder(folder: Path) -> None:
    skip = shutil.ignore_patterns(*IGNORED)(str(folder), [part.name for part in folder.iterdir()])
    for path in folder.iterdir():
        if path.name in skip:
            continue
        if path.is_symlink():
            raise ValueError(f"模板来源包含符号链接：{path}")
        if path.is_dir():
            check_folder(path)


def initialize(source: Path, target: Path, name: str) -> None:
    if not name.strip():
        raise ValueError("产品名称不能为空")
    if target.exists() or target.is_symlink() or target.resolve().is_relative_to(source.resolve()):
        raise ValueError("目标必须是模板目录之外尚不存在的新目录")
    check_source(source)
    target.mkdir(parents=True)
    try:
        for entry in ENTRIES:
            original = source / entry
            if original.is_dir():
                shutil.copytree(original, target / entry, ignore=shutil.ignore_patterns(*IGNORED))
            elif original.is_file():
                shutil.copy2(original, target / entry)
        native_documents(source, target, name.strip())
        save_provenance(target, source)
    except (OSError, ValueError, KeyError):
        shutil.rmtree(target)
        raise


def native_documents(source: Path, target: Path, name: str) -> None:
    product_entry(target, name)
    product_metadata(source, target)
    product_configuration(target, name)


def product_entry(target: Path, name: str) -> None:
    write(
        target / "server/app/product.py",
        "from shared.application.spec import ApplicationSpec\n\n"
        f"APPLICATION = ApplicationSpec(name={json.dumps(name, ensure_ascii=False)})\n",
    )
    write(
        target / "README.md",
        f"# {name}\n\n开发入口见 [AGENTS.md](AGENTS.md)。\n\n```bash\ncd server\nuv sync\n"
        "cp .env.example .env\nuv run alembic upgrade head\n"
        "uv run uvicorn app.setup.web:create_app --factory --reload --no-access-log\n```\n\n"
        "完整检查：`uv run dev check`。\n"
        "框架来源见 [template-source.json](template-source.json)，"
        "更新方法见 [UPGRADING](.agents/skills/fastapi-template/references/upgrading.md)。\n",
    )
    write(
        target / "CHANGELOG.md",
        f"# {name}：版本记录\n\n## 0.1.0\n\n从通用后端模板初始化，尚未完成产品业务。"
        "框架来源见 template-source.json。\n",
    )
    agents = (target / "AGENTS.md").read_text(encoding="utf-8")
    write(target / "AGENTS.md", f"# {name}\n\n" + agents[agents.index("## 业务要点") :])


def product_metadata(source: Path, target: Path) -> None:
    version = provenance(source)["version"]
    metadata = target / "server/pyproject.toml"
    text = (
        metadata.read_text(encoding="utf-8")
        .replace('name = "fastapi-server-template"', 'name = "product-server"')
        .replace(f'version = "{version}"', 'version = "0.1.0"', 1)
        .replace(
            'description = "便于人审查、便于 AI 按固定结构开发的 FastAPI 单体后端模板"',
            'description = "产品后端"',
            1,
        )
    )
    write(metadata, text)
    lock = target / "server/uv.lock"
    original = f'name = "fastapi-server-template"\nversion = "{version}"'
    write(
        lock,
        lock.read_text(encoding="utf-8").replace(
            original, 'name = "product-server"\nversion = "0.1.0"', 1
        ),
    )


def product_configuration(target: Path, name: str) -> None:
    configuration = target / "server/.env.example"
    write(
        configuration,
        "".join(
            f"APP_NAME={json.dumps(name, ensure_ascii=False)}\n"
            if line.startswith("APP_NAME=")
            else line
            for line in configuration.read_text(encoding="utf-8").splitlines(keepends=True)
        ),
    )


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
