import secrets
from datetime import UTC, datetime
from pathlib import Path
from string import Template

from alembic.script import ScriptDirectory
from alembic.util import CommandError
from fastapi_check.quality.rules import ROOT
from fastapi_module.new_module import camel

TEMPLATES = Path(__file__).resolve().parents[2] / "assets/templates/access"


def preset_targets(name: str, revision: str) -> dict[Path, Path]:
    places = {
        "service": ROOT / "service" / name,
        "tests/modules": ROOT / "tests/modules" / name,
        "tests/integration": ROOT / "tests/integration" / name,
    }
    day = datetime.now(UTC).strftime("%Y%m%d")
    fixed = {
        "api.py": ROOT / "app/api/v1" / f"{name}.py",
        "migration.py": ROOT / "migrations/versions" / f"{day}_{revision}_{name}_accounts.py",
    }
    targets = {}
    for source in sorted(TEMPLATES.rglob("*.txt")):
        relative = source.relative_to(TEMPLATES).as_posix().removesuffix(".txt")
        area = next((key for key in places if relative.startswith(key + "/")), "")
        targets[source] = fixed[relative] if not area else places[area] / relative[len(area) + 1 :]
    return targets


def migration_head() -> str | None:
    try:
        return ScriptDirectory(str(ROOT / "migrations")).get_current_head()
    except CommandError as error:
        raise SystemExit(f"迁移有多个头，请先合并迁移再生成账号包：{error}") from error


def write_preset(name: str, title: str) -> list[Path]:
    revision = secrets.token_hex(6)
    head = migration_head()
    values = {
        "name": name,
        "title": title,
        "Camel": camel(name),
        "revision": revision,
        "down_revision": repr(head),
        "previous": head or "无",
    }
    written = []
    for source, target in preset_targets(name, revision).items():
        text = Template(source.read_text(encoding="utf-8")).substitute(values)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        written.append(target)
    return written


def next_steps(name: str) -> list[str]:
    return [
        "1. 确认登录规则；角色、停用、改口令等按产品需要再加",
        "2. uv run alembic upgrade head（账号表的迁移已经生成）",
        f"3. uv run dev make-key --name 账号管理 --org-id 组织代码 --permissions {name}.manage，"
        "把摘要配置进 APP_API_KEYS，再用它调用 POST /api/v1/access/accounts 建第一个账号",
        "4. uv run dev docs（更新 openapi.json）",
        f"5. uv run dev check --module {name}（先检查本模块）",
        "6. uv run dev check（交付前检查全部模块）",
    ]
