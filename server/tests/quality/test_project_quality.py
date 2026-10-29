import json
import os

from fastapi_check.quality.blocking import check_blocking
from fastapi_check.quality.docs import check_business_docs, check_writing_style
from fastapi_check.quality.files import check_files
from fastapi_check.quality.naming import check_naming
from fastapi_check.quality.readmes import check_readmes
from fastapi_check.quality.report import Problem, in_modules, unused_allowed, without_allowed

from app.setup.catalog import MODULES
from shared.modules.catalog import Catalog


def listed(problems: list[Problem]) -> str:
    return "\n".join(problem.text() for problem in problems)


def selected() -> list[str]:
    return json.loads(os.environ.get("APP_DEVELOPMENT_MODULES", "[]"))


def scoped(problems: list[Problem]) -> list[Problem]:
    return in_modules(without_allowed(problems), selected())


def test_code_style() -> None:
    problems = scoped(check_files())
    assert problems == [], listed(problems)


def test_naming() -> None:
    problems = scoped(check_naming())
    assert problems == [], listed(problems)


def test_no_blocking_calls() -> None:
    problems = scoped(check_blocking())
    assert problems == [], listed(problems)


def test_readmes() -> None:
    catalog = Catalog(MODULES)
    names = {
        name: [item.name for item in module.provides] for name, module in catalog.modules.items()
    }
    problems = scoped(check_readmes(contracts=names))
    assert problems == [], listed(problems)


def test_business_docs() -> None:
    problems = scoped(check_business_docs(Catalog(MODULES)))
    assert problems == [], listed(problems)


def test_writing_style() -> None:
    problems = scoped(check_writing_style())
    assert problems == [], listed(problems)


def test_no_stale_exceptions() -> None:
    everything = check_files() + check_naming() + check_blocking()
    assert in_modules(unused_allowed(everything), selected()) == []
