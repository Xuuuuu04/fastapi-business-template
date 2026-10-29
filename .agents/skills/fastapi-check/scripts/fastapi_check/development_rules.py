from fastapi_check.quality.docs import check_development_rules
from fastapi_check.quality.rules import PROJECT

from app.setup.application import application_modules
from shared.modules.catalog import Catalog


def check_development(delivery: bool) -> list[str]:
    problems = check_development_rules(Catalog(application_modules()), PROJECT, delivery=delivery)
    texts = [problem.text() for problem in problems]
    for text in texts:
        print(text, flush=True)
    return texts
