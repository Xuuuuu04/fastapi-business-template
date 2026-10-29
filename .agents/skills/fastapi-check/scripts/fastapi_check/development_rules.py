from app.setup.application import application_modules
from shared.modules.catalog import Catalog


def simulated_steps(catalog: Catalog) -> list[str]:
    return [
        f"service/{binding.module.name}：交付不能包含模拟骨架：{binding.contract.name}"
        for binding in catalog.bindings.values()
        if any(part.simulated for part in binding.flow.steps)
    ]


def check_development(delivery: bool) -> list[str]:
    texts = simulated_steps(Catalog(application_modules())) if delivery else []
    for text in texts:
        print(text, flush=True)
    return texts
