import hashlib
import json
from pathlib import Path

from fastapi_project.development.history import dependency_modules
from fastapi_project.development.ledger import ledger_digest, read_ledger

from shared.modules.catalog import Catalog


def scope_modules(catalog: Catalog, package: str) -> list[str]:
    return dependency_modules(package, catalog.links())


def rules_digest(project: Path, modules: list[str] | None = None) -> str:
    ledger = read_ledger(project)
    if modules is None:
        return ledger_digest(ledger)
    rules = [rule for rule in ledger.rules if rule.id.split(".")[0] in modules]
    sources = {source for rule in rules for source in rule.sources}
    shape = {
        "rules": [rule.model_dump(mode="json") for rule in rules],
        "sources": [
            source.model_dump(mode="json") for source in ledger.sources if source.id in sources
        ],
    }
    return hashlib.sha256(json.dumps(shape, sort_keys=True).encode()).hexdigest()
