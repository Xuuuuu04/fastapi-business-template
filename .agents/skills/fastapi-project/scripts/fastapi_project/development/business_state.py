"""
本机业务现状：生成声明/运行事实与手写判断分开，检查源码版本和生成时间，不把未知补成成功。
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from fastapi_project.development.history import fingerprints
from sqlalchemy.engine import make_url

from shared.modules.catalog import Catalog
from shared.modules.digest import digest_of

BEGIN = "<!-- fastapi-business-state:begin -->"
END = "<!-- fastapi-business-state:end -->"
META = "<!-- business-state-meta:"
MAX_AGE = 86400
FOLDER = ".agents/records/business-state"
MANUAL = "\n## 手写部分\n\n- 业务判断：未知。\n- 外部依赖：未知。\n- 下一步：待填写。\n"


# 库目标仅保留无密码的单向摘要，换库/角色/搜索路径后旧观察过期，不泄露连接目标。
def database_identity(url: str) -> str:
    parsed = make_url(url).set(password=None)
    if parsed.get_backend_name() == "sqlite" and parsed.database and parsed.database != ":memory:":
        parsed = parsed.set(database=str(Path(parsed.database).resolve()))
    return hashlib.sha256(parsed.render_as_string(hide_password=True).encode()).hexdigest()


# 模块声明包含普通/分段/流程与关键任务选择，不根据操作数量推测完成度。
def declaration(catalog: Catalog, name: str, disabled: set[str]) -> dict[str, Any]:
    module = catalog.modules[name]
    return dict(
        name=name,
        title=module.title,
        version=module.version,
        signature=digest_of([module]),
        disabled=name in disabled,
        operations=[item.name for item in module.provides if item.entry],
        jobs=[
            dict(name=plan.contract.name, segmented=plan.segmented, critical=plan.critical)
            for plan in module.jobs
        ],
        schedules=[
            dict(
                name=plan.name,
                operation=plan.contract.name,
                every_seconds=plan.every.total_seconds() if plan.every else None,
                daily_at=plan.daily_at.isoformat() if plan.daily_at else None,
                zone=plan.zone,
            )
            for plan in module.schedules
        ],
        pipelines=[
            dict(name=plan.name, stages=[part.name for part in plan.stages])
            for plan in module.pipelines
        ],
    )


# 只读取生成标记之间的元信息；坏记录明确报错，不覆盖手写判断。
def read(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    text = path.read_text()
    if text.count(BEGIN) != 1 or text.count(END) != 1 or text.count(META) != 1:
        raise ValueError(f"业务现状生成标记不完整：{path}")
    if not text.index(BEGIN) < text.index(META) < text.index(END):
        raise ValueError(f"业务现状生成标记顺序错误：{path}")
    header = json.loads(text.split(META, 1)[1].split(" -->", 1)[0])
    data = json.loads(path.with_suffix(".json").read_text())
    if header != metadata(data):
        raise ValueError(f"业务现状摘要与明细不一致：{path}")
    return data


# Markdown只放短元信息，完整生成明细在同名JSON，不要求代理开工展开全文。
def metadata(data: dict[str, Any]) -> dict[str, Any]:
    digest = hashlib.sha256(
        json.dumps(data, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    return dict(
        schema=1, generated_at=data["generated_at"], fingerprint=data["fingerprint"], payload=digest
    )


# 一屏优先，长清单明确省略数量，完整操作通过project详情深入。
def preview(items: list[str], maximum: int = 8) -> str:
    if not items:
        return "无"
    result = "、".join(items[:maximum])
    return result + (
        f"（另有{len(items) - maximum}项，使用project --module查看）"
        if len(items) > maximum
        else ""
    )


# 运行摘要最多展开三个实例/流程，完整明细在同名JSON。
def fact_preview(value: Any) -> str:
    if not isinstance(value, dict):
        return str(value)
    value = dict(value)
    if "examples" in value:
        rows = value["examples"]
        value["examples"] = rows[:3]
        value["omitted"] = value.get("omitted", 0) + max(0, len(rows) - 3)
    if "pipelines" in value:
        rows = list(value["pipelines"].items())
        value["pipelines"] = dict(rows[:3])
        value["omitted_pipelines"] = max(0, len(rows) - 3)
    return json.dumps(value, ensure_ascii=False)


# 运行部分仅保存状态/编号/时间/数量，不保存业务输入、SQL参数或连接目标。
def block(data: dict[str, Any]) -> str:
    declared = data["declaration"]
    runtime = data["runtime"]
    lines = [
        BEGIN,
        "## 生成部分（命令维护）",
        "",
        "登记不等于业务完成；未知不等于未运行，观察不是业务验收。",
        f"模块：{declared['name']} / {declared['title']} / {declared['version']}；"
        + ("已关闭" if declared["disabled"] else "启用"),
        "操作：" + preview(declared["operations"]),
        "后台："
        + preview(
            [
                item["name"] + ("（分段）" if item["segmented"] else "（普通）")
                for item in declared["jobs"]
            ]
        ),
        "定时："
        + preview([item["name"] + " → " + item["operation"] for item in declared["schedules"]]),
        "流程："
        + preview(
            [
                item["name"] + "（" + " → ".join(item["stages"]) + "）"
                for item in declared["pipelines"]
            ]
        ),
        "最近运行：" + fact_preview(runtime["last"]),
        "逾期：" + fact_preview(runtime["overdue"]),
        "待确认：" + fact_preview(runtime["confirmation"]),
        "观察时刻：" + str(runtime.get("observed_at") or "未知：尚未读取数据库"),
        "生成时刻：" + str(data["generated_at"]),
        "深入：project --module "
        + declared["name"]
        + " --summary；project --module "
        + declared["name"]
        + " --runs。",
        META + json.dumps(metadata(data), ensure_ascii=False, separators=(",", ":")) + " -->",
        END,
    ]
    return "\n".join(lines)


# 不访问数据库时如实未知；显式不读取不会把旧证据当当前真实状态。
def unknown() -> dict[str, Any]:
    return dict(
        last="未知：未读取数据库",
        overdue="未知：未读取数据库",
        confirmation="未知：未读取数据库",
        observed_at=None,
    )


# 保留生成区之外的原字节，文件缺失时才建立手写占位。
def render(path: Path, data: dict[str, Any]) -> str:
    if not path.exists():
        return "# 业务现状：" + data["declaration"]["name"] + "\n\n" + block(data) + "\n" + MANUAL
    text = path.read_text()
    if text.count(BEGIN) != 1 or text.count(END) != 1 or text.index(BEGIN) >= text.index(END):
        raise ValueError(f"业务现状生成边界损坏，先保留并修复手写部分：{path}")
    first, last = text.index(BEGIN), text.index(END) + len(END)
    return text[:first] + block(data) + text[last:]


# 源码与依赖变化、声明变化、生成超过一天都过期；check只比较，绝不自动刷新证据。
def outdated(
    catalog: Catalog,
    project: Path,
    disabled: set[str],
    now: float | None = None,
    database_id: str | None = None,
) -> list[Path]:
    now = time.time() if now is None else now
    versions = fingerprints(project, list(catalog.modules), catalog.links())
    result = []
    for name in catalog.modules:
        path = project / FOLDER / f"{name}.md"
        try:
            saved = read(path)
            stale = (
                not saved
                or saved["fingerprint"] != versions[name]
                or saved["declaration"] != declaration(catalog, name, disabled)
                or not 0 <= now - saved["generated_at"] <= MAX_AGE
                or (
                    database_id is not None
                    and saved["runtime"].get("observed_at") is not None
                    and saved["runtime"].get("database_id") != database_id
                )
                or path.read_text().split(BEGIN, 1)[1].split(END, 1)[0]
                != block(saved).split(BEGIN, 1)[1].split(END, 1)[0]
            )
        except (OSError, ValueError, KeyError, TypeError):
            stale = True
        if stale:
            result.append(path)
    return result


# 显式命令生成；缺少DB证据标未知，不改手写部分。
def update(
    catalog: Catalog,
    project: Path,
    disabled: set[str],
    runtime: dict[str, Any] | None = None,
    names: list[str] | None = None,
) -> list[Path]:
    versions = fingerprints(project, list(catalog.modules), catalog.links())
    paths = []
    now = time.time()
    for name in names if names is not None else catalog.modules:
        path = project / FOLDER / f"{name}.md"
        data = dict(
            schema=1,
            generated_at=now,
            fingerprint=versions[name],
            declaration=declaration(catalog, name, disabled),
            runtime=(runtime or {}).get(name, unknown()),
        )
        text = render(path, data)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.with_suffix(".json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
        path.write_text(text)
        paths.append(path)
    return paths
