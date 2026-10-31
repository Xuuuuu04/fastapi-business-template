from app.setup.application import application_modules
from shared.modules.catalog import Catalog


def unfinished_steps(catalog: Catalog) -> list[str]:
    return [
        f"{part.source}：交付时必须把占位或模拟步骤替换为真实实现：“{part.title}”（{binding.contract.name}）"
        for binding in catalog.bindings.values()
        for part in binding.flow.steps
        if part.simulated or part.placeholder
    ]


def check_development(delivery: bool) -> list[str]:
    texts = unfinished_steps(Catalog(application_modules())) if delivery else []
    for text in texts:
        print(text, flush=True)
    return texts
