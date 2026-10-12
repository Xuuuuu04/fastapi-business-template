"""
规则与项目计划按业务身份做三方合并，冲突不猜取舍，来源与确认语义完整保留。
"""

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from fastapi_project.development.check_assets import atomic_bytes
from fastapi_project.development.ledger_models import RuleLedger
from fastapi_project.development.ledger_store import INDEX, decode_ledger, store_files
from fastapi_project.development.ledger_store_models import parse_index
from fastapi_project.development.plan import check_plan
from fastapi_template.template.files import safe_path


# Git原件取自明确提交，不读取工作树里尚未处理的冲突标记。
def blob(project: Path, commit: str, name: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", commit + ":" + name],
        cwd=project,
        capture_output=True,
        check=False,
        timeout=15,
    )
    if result.returncode == 128:
        return None
    if result.returncode:
        raise ValueError("不能读取整合原件：" + name)
    return result.stdout


# 同一身份双方都改成不同内容时拒绝；一边未变则使用真正改动的一边。
def choose(old: Any, local: Any, incoming: Any, location: str) -> Any:
    if local == incoming or incoming == old:
        return local
    if local == old:
        return incoming
    raise ValueError("语义冲突需要处理：" + location)


# 当前规则与脱敏来源按ID合并，删除与修订竞争不被列表顺序掩盖。
def identity_merge(
    old: list[dict], local: list[dict], incoming: list[dict], key: str
) -> list[dict]:
    maps = [{item[key]: item for item in values} for values in (old, local, incoming)]
    if any(
        len(mapping) != len(values)
        for mapping, values in zip(maps, (old, local, incoming), strict=True)
    ):
        raise ValueError("语义合并包含重复身份")
    result = []
    for identity in sorted(maps[0].keys() | maps[1].keys() | maps[2].keys()):
        value = choose(
            maps[0].get(identity), maps[1].get(identity), maps[2].get(identity), str(identity)
        )
        if value is not None:
            result.append(value)
    return result


# 两种账本原件均汇总为同一模型，旧资料不会在合并中被自动标为确认。
def committed_ledger(project: Path, commit: str) -> RuleLedger:
    content = blob(project, commit, INDEX)
    if content is None:
        return RuleLedger()
    index = parse_index(content)
    packages = {}
    for name in index.get("packages", []):
        raw = blob(project, commit, f"doc/{name}/rules.json")
        if raw is None:
            raise ValueError("分包规则Git原件缺失")
        packages[name] = json.loads(raw)
    return decode_ledger(index, packages)


# 当前状态三方合并，完整历史用事件内容摘要去重，不以新generation选择业务事实。
def merge_ledgers(project: Path, commits: tuple[str, str, str]) -> dict[str, str]:
    ledgers = [committed_ledger(project, commit).model_dump(mode="json") for commit in commits]
    sources = identity_merge(
        ledgers[0]["sources"], ledgers[1]["sources"], ledgers[2]["sources"], "id"
    )
    rules = identity_merge(ledgers[0]["rules"], ledgers[1]["rules"], ledgers[2]["rules"], "id")
    events = {}
    for ledger in ledgers:
        for event in ledger["events"]:
            digest = hashlib.sha256(json.dumps(event, sort_keys=True).encode()).hexdigest()
            events[digest] = event
    merged = RuleLedger(sources=sources, rules=rules, events=list(events.values()))
    merged.validate_links()
    if not any(blob(project, commit, INDEX) is not None for commit in commits):
        return {}
    return store_files(project, merged)


# 计划集合按显式增删合并；同包说明或归属冲突需要处理，不猜业务目的。
def plan_value(old: Any, local: Any, incoming: Any, location: str) -> Any:
    if local in (incoming, old) or incoming == old:
        return choose(old, local, incoming, location)
    if all(isinstance(value, dict) for value in (old, local, incoming)):
        return {
            key: plan_value(old.get(key), local.get(key), incoming.get(key), location + "." + key)
            for key in sorted(old.keys() | local.keys() | incoming.keys())
        }
    if location.endswith((".operations", ".dependencies", ".implemented_operations")) and all(
        isinstance(value, list) for value in (old, local, incoming)
    ):
        removed = (set(old) - set(local)) | (set(old) - set(incoming))
        return sorted((set(local) | set(incoming)) - removed)
    return choose(old, local, incoming, location)


# 包名是唯一业务身份，计划中的未实现包保留，不按当前代码缩减用户目标。
def merge_plans(values: list[dict]) -> dict:
    packages = [
        {
            package["module"]: {"line": line["name"], "package": package}
            for line in value["lines"]
            for package in line["packages"]
        }
        for value in values
    ]
    merged = plan_value(packages[0], packages[1], packages[2], "packages")
    lines: dict[str, list[dict]] = {}
    for item in merged.values():
        if item is not None:
            lines.setdefault(item["line"], []).append(item["package"])
    plan = {
        "schema_version": max(value["schema_version"] for value in values),
        "name": choose(values[0]["name"], values[1]["name"], values[2]["name"], "项目名称"),
        "lines": [{"name": name, "packages": items} for name, items in lines.items()],
    }
    check_plan(plan)
    return plan


# 所有内容先计算成功再落到临时树，原工作区仍由整合生命周期保护。
def resolve_json(project: Path, commits: tuple[str, str, str]) -> list[str]:
    files = merge_ledgers(project, commits)
    plans = [blob(project, commit, "project-plan.json") for commit in commits]
    if any(plans):
        values = [
            json.loads(value) if value else {"schema_version": 2, "name": "新项目", "lines": []}
            for value in plans
        ]
        files["project-plan.json"] = (
            json.dumps(merge_plans(values), ensure_ascii=False, indent=2) + "\n"
        )
    for name, text in files.items():
        atomic_bytes(safe_path(project, name), text.encode())
    return sorted(files)
