import hashlib
import json
import time
from pathlib import Path
from typing import Any

from fastapi_project.development.business_state_text import (
    attention_text,
    footer_text,
    jobs_text,
    last_text,
    preview,
    schedule_text,
    time_text,
)
from fastapi_project.development.history import fingerprints
from sqlalchemy.engine import make_url

from shared.modules.catalog import Catalog
from shared.modules.digest import digest_of

BEGIN = "<!-- fastapi-business-state:begin -->"
END = "<!-- fastapi-business-state:end -->"
META = "<!-- business-state-meta:"
MAX_AGE = 86400
FOLDER = ".agents/records/business-state"
MANUAL = (
    "\n## 手写部分\n\n"
    "这一部分由人填写，命令刷新时不会覆盖它。请写人能直接读懂的完整句子，"
    "不要用只有自己知道的编号和缩写。\n\n"
    "- 业务判断：这个模块在业务上现在是什么状态。\n"
    "- 外部依赖：依赖哪些外部系统或人工步骤。\n"
    "- 下一步：接下来要做什么、现在卡在哪里。\n"
)


def database_identity(url: str) -> str:
    parsed = make_url(url).set(password=None)
    if parsed.get_backend_name() == "sqlite" and parsed.database and parsed.database != ":memory:":
        parsed = parsed.set(database=str(Path(parsed.database).resolve()))
    return hashlib.sha256(parsed.render_as_string(hide_password=True).encode()).hexdigest()


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


def metadata(data: dict[str, Any]) -> dict[str, Any]:
    digest = hashlib.sha256(
        json.dumps(data, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    return dict(
        schema=1, generated_at=data["generated_at"], fingerprint=data["fingerprint"], payload=digest
    )


def block(data: dict[str, Any]) -> str:
    declared = data["declaration"]
    runtime = data["runtime"]
    state = "已关闭" if declared["disabled"] else "启用"
    lines = [
        BEGIN,
        "## 生成部分（命令维护）",
        "",
        "下面是命令自动生成的登记和观察事实。登记只说明代码里有了它，不代表业务已经完成；",
        "查不到的写“未知”，不代表没有发生过；观察到的成功，也不能代替业务验收。",
        "",
        f"- **模块**：{declared['title']}（{declared['name']}），"
        f"版本 {declared['version']}，当前{state}。",
        "- **对外操作**：共 "
        + str(len(declared["operations"]))
        + " 个："
        + preview(declared["operations"]),
        f"- **后台任务**：{jobs_text(declared)}",
        "- **定时入口**："
        + (
            "、".join(schedule_text(item) for item in declared["schedules"])
            if declared["schedules"]
            else "无"
        ),
        "- **多阶段流程**："
        + (
            "；".join(
                f"{item['name']}（{' → '.join(item['stages'])}）" for item in declared["pipelines"]
            )
            if declared["pipelines"]
            else "无"
        ),
        "- **最近运行**：" + last_text(runtime["last"]),
        "- **逾期情况**：" + attention_text(runtime["overdue"], "逾期"),
        "- **待确认的任务**：" + attention_text(runtime["confirmation"], "结果待确认"),
        f"- **观察时刻**：{time_text(runtime.get('observed_at'))}；"
        f"生成时刻：{time_text(data['generated_at'])}。",
        footer_text(declared["name"]),
        META + json.dumps(metadata(data), ensure_ascii=False, separators=(",", ":")) + " -->",
        END,
    ]
    return "\n".join(lines)


def unknown() -> dict[str, Any]:
    message = "未知（还没有连接数据库读取过）"
    return dict(
        last=message,
        overdue=message,
        confirmation=message,
        observed_at=None,
    )


def render(path: Path, data: dict[str, Any]) -> str:
    if not path.exists():
        return "# 业务现状：" + data["declaration"]["name"] + "\n\n" + block(data) + "\n" + MANUAL
    text = path.read_text()
    if text.count(BEGIN) != 1 or text.count(END) != 1 or text.index(BEGIN) >= text.index(END):
        raise ValueError(f"业务现状生成边界损坏，先保留并修复手写部分：{path}")
    first, last = text.index(BEGIN), text.index(END) + len(END)
    return text[:first] + block(data) + text[last:]


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
                or now < saved["generated_at"]
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
