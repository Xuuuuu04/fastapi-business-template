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
    "project-plan.json",
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
            raise ValueError(f"来源包含链接：{path}")
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
    product_history(target, name)
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
        f"# {name}\n\n业务计划见 [project-plan.json](project-plan.json)，"
        "开发入口见 [AGENTS.md](AGENTS.md)。\n\n```bash\ncd server\nuv sync\n"
        "cp .env.example .env\nuv run alembic upgrade head\n"
        "uv run uvicorn app.setup.web:create_app --factory --reload --no-access-log\n```\n\n"
        "开发摘要：`uv run dev status --summary --json`；完整检查：`uv run dev check`。\n"
        "框架来源见 [template-source.json](template-source.json)，"
        "更新方法见 [UPGRADING](.agents/skills/fastapi-template/references/upgrading.md)。\n",
    )
    write(
        target / "CHANGELOG.md",
        f"# {name}：版本记录\n\n## 0.1.0\n\n从通用后端模板初始化，尚未完成产品业务。"
        "框架来源见 template-source.json。\n",
    )
    write(
        target / "project-plan.json",
        json.dumps({"schema_version": 1, "name": name, "lines": []}, ensure_ascii=False, indent=2)
        + "\n",
    )
    write(
        target / "doc/tasks.md",
        "# 任务清单\n\n- [ ] 产品：填写业务线与开发包，生成所需业务模块\n"
        "- [ ] 上线前：按实际环境验证数据库、权限、容量和恢复过程\n",
    )
    agents = (target / "AGENTS.md").read_text(encoding="utf-8")
    end = agents.index("## 怎么运行")
    agents = (
        f"# {name}\n\n"
        + f"## 这个项目是什么\n\n- 产品：{name}\n- 使用者：（待填写）\n"
        + "- 主要模块：见 [doc/README.md](doc/README.md)；"
        "预先设计见 [project-plan.json](project-plan.json)\n\n"
        "业务模块由产品按需要生成，规则须按本产品确认。\n\n" + agents[end:]
    )
    write(target / "AGENTS.md", agents)


def product_history(target: Path, name: str) -> None:
    for path in (target / "doc").glob("*/changes.md"):
        write(
            path,
            f"# {path.parent.name}：业务变化\n\n从模板继承通用模块规则；"
            "产品中的调整从这里开始记录。\n",
        )
    deploy = target / "server/deploy/README.md"
    write(
        deploy,
        deploy.read_text(encoding="utf-8").split("## 精简前的生产配置验收记录")[0].rstrip() + "\n",
    )


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
