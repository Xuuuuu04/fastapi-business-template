import json
import re
import uuid
from pathlib import Path

from fastapi_project.development.check_assets import atomic_bytes
from fastapi_project.development.ledger_lock import serialized
from fastapi_project.development.ledger_models import RuleLedger
from fastapi_project.development.ledger_store_models import PackageRules, parse_index, parse_write
from fastapi_template.template.files import safe_path

INDEX = "doc/rules-ledger.json"
JOURNAL = ".agents/records/ledger-write.json"
PACKAGE = re.compile(r"^[a-z][a-z0-9_]*$")


def original_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def rule_path(project: Path, name: str) -> Path:
    if not PACKAGE.fullmatch(name):
        raise ValueError("规则包名不合法")
    return safe_path(project, f"doc/{name}/rules.json")


def store_files(project: Path, ledger: RuleLedger) -> dict[str, str]:
    names = sorted(
        {item.id.split(".")[0] for item in ledger.rules}
        | {event.rule.split(".")[0] for event in ledger.events}
    )
    result = {}
    for name in names:
        path = rule_path(project, name)
        value = {
            "schema_version": 1,
            "rules": [
                rule.model_dump(mode="json")
                for rule in ledger.rules
                if rule.id.startswith(name + ".")
            ],
            "events": [
                event.model_dump(mode="json")
                for event in ledger.events
                if event.rule.startswith(name + ".")
            ],
        }
        result[path.relative_to(project).as_posix()] = (
            json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        )
    result[INDEX] = (
        json.dumps(
            {
                "schema_version": 2,
                "generation": uuid.uuid4().hex,
                "packages": names,
                "sources": [source.model_dump(mode="json") for source in ledger.sources],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    return result


def decode_ledger(index: dict, packages: dict[str, dict]) -> RuleLedger:
    if index.get("schema_version") == 1:
        ledger = RuleLedger.model_validate(index)
    elif index.get("schema_version") == 2:
        if set(index.get("packages", [])) != packages.keys():
            raise ValueError("分包规则与索引不一致，请恢复写入或重建合并索引")
        rules, events = [], []
        for name, data in packages.items():
            if not PACKAGE.fullmatch(name):
                raise ValueError("分包规则格式不合法")
            package = PackageRules.model_validate(data)
            part = RuleLedger.model_validate(
                {
                    "sources": index.get("sources", []),
                    "rules": package.rules,
                    "events": package.events,
                }
            )
            if any(not rule.id.startswith(name + ".") for rule in part.rules) or any(
                not event.rule.startswith(name + ".") for event in part.events
            ):
                raise ValueError("规则或事件不属于声明的包")
            rules.extend(part.rules)
            events.extend(part.events)
        ledger = RuleLedger(sources=index.get("sources", []), rules=rules, events=events)
    else:
        raise ValueError("规则账本格式不支持")
    ledger.validate_links()
    return ledger


def journal_ledger(project: Path) -> RuleLedger | None:
    path = safe_path(project, JOURNAL)
    if not path.exists():
        return None
    data = parse_write(path.read_bytes())
    target = safe_path(project, INDEX)
    committed = target.is_file() and original_text(target) == data["after_files"][INDEX]
    ledger = RuleLedger.model_validate(data["after"] if committed else data["before"])
    ledger.validate_links()
    return ledger


def package_data(project: Path, index: dict) -> dict[str, dict]:
    if index.get("schema_version") != 2:
        return {}
    return {
        name: json.loads(rule_path(project, name).read_text()) for name in index.get("packages", [])
    }


def read_once(project: Path) -> RuleLedger | None:
    path = safe_path(project, INDEX)
    if not path.is_file():
        if list((project / "doc").glob("*/rules.json")):
            if path.is_file() or (project / JOURNAL).exists():
                return None
            raise ValueError("存在未登记的分包规则，请先导入或恢复索引")
        return RuleLedger()
    content = path.read_bytes()
    index = parse_index(content)
    try:
        actual = {item.parent.name for item in (project / "doc").glob("*/rules.json")}
        if actual != set(index.get("packages", [])):
            raise ValueError("分包规则清单未登记，请先恢复或合并索引")
        packages = package_data(project, index)
    except (OSError, ValueError):
        if (project / JOURNAL).exists() or path.read_bytes() != content:
            return None
        raise
    if (project / JOURNAL).exists() or path.read_bytes() != content:
        return None
    return decode_ledger(index, packages)


def read_store(project: Path) -> RuleLedger:
    for _ in range(3):
        snapshot = journal_ledger(project)
        if snapshot is not None:
            return snapshot
        snapshot = read_once(project)
        if snapshot is not None:
            return snapshot
    raise ValueError("规则账本正在变化，请稍后读取")


def checked_file(project: Path, name: str) -> Path:
    if name != INDEX and not re.fullmatch(r"doc/[a-z][a-z0-9_]*/rules\.json", name):
        raise ValueError("规则写入日志包含非法文件")
    return safe_path(project, name)


def restore_files(project: Path, desired: dict, alternatives: dict) -> None:
    for name in desired.keys() | alternatives.keys():
        path = checked_file(project, name)
        current = original_text(path) if path.is_file() else None
        if current not in (desired.get(name), alternatives.get(name)):
            raise ValueError("规则原件在写入后被修改，不能自动恢复：" + name)
    for name, content in desired.items():
        path = checked_file(project, name)
        if content is None:
            path.unlink(missing_ok=True)
        else:
            atomic_bytes(path, content.encode())


@serialized
def recover_store(project: Path) -> bool:
    path = safe_path(project, JOURNAL)
    if not path.exists():
        return False
    data = parse_write(path.read_bytes())
    current = checked_file(project, INDEX)
    committed = current.is_file() and original_text(current) == data["after_files"][INDEX]
    desired, alternatives = (
        (data["after_files"], data["before_files"])
        if committed
        else (data["before_files"], data["after_files"])
    )
    restore_files(project, desired, alternatives)
    path.unlink()
    return True


@serialized
def write_store(project: Path, ledger: RuleLedger) -> Path:
    recover_store(project)
    ledger.validate_links()
    before = read_store(project)
    targets = store_files(project, ledger)
    existing = {
        path.relative_to(project).as_posix() for path in (project / "doc").glob("*/rules.json")
    }
    names = existing | targets.keys() | {INDEX}
    before_files = {
        name: original_text(checked_file(project, name))
        if checked_file(project, name).is_file()
        else None
        for name in names
    }
    after_files: dict[str, str | None] = {name: targets.get(name) for name in names}
    journal = {
        "schema_version": 1,
        "before": before.model_dump(mode="json"),
        "after": ledger.model_dump(mode="json"),
        "before_files": before_files,
        "after_files": after_files,
    }
    atomic_bytes(
        safe_path(project, JOURNAL), json.dumps(journal, ensure_ascii=False, indent=2).encode()
    )
    try:
        for name in sorted(names - {INDEX}):
            target = checked_file(project, name)
            content = after_files[name]
            if content is None:
                target.unlink(missing_ok=True)
            elif content != before_files[name]:
                atomic_bytes(target, content.encode())
        atomic_bytes(checked_file(project, INDEX), targets[INDEX].encode())
    except Exception:
        restore_files(project, before_files, after_files)
        (project / JOURNAL).unlink()
        raise
    (project / JOURNAL).unlink()
    return checked_file(project, INDEX)
