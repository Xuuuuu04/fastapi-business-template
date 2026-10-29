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


def choose(old: Any, local: Any, incoming: Any, location: str) -> Any:
    if local == incoming or incoming == old:
        return local
    if local == old:
        return incoming
    raise ValueError("语义冲突需要处理：" + location)


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
    line_values = [[{"id": line["name"]} for line in value["lines"]] for value in values]
    declared = identity_merge(line_values[0], line_values[1], line_values[2], "id")
    lines: dict[str, list[dict]] = {line["id"]: [] for line in declared}
    for item in merged.values():
        if item is not None:
            if item["line"] not in lines:
                raise ValueError("业务线删除与另一侧新增或修改包冲突：" + item["line"])
            lines[item["line"]].append(item["package"])
    plan = {
        "schema_version": max(value["schema_version"] for value in values),
        "name": choose(values[0]["name"], values[1]["name"], values[2]["name"], "项目名称"),
        "lines": [{"name": name, "packages": items} for name, items in lines.items()],
    }
    check_plan(plan)
    return plan


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
