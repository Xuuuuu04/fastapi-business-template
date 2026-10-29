from pathlib import Path

from shared.application.spec import ApplicationSpec
from shared.errors.framework import ConfigError
from shared.modules.libraries import LibrarySpec, library_specs
from shared.modules.module import Module


def application() -> ApplicationSpec:
    from app.product import APPLICATION

    if not isinstance(APPLICATION, ApplicationSpec):
        raise ConfigError(["app.product.APPLICATION必须是ApplicationSpec"])
    APPLICATION.validate()
    return APPLICATION


def application_modules() -> tuple[Module, ...]:
    from app.setup.catalog import MODULES

    declared = application().modules
    return tuple(MODULES) if declared is None else declared


def application_libraries() -> list[LibrarySpec]:
    return library_specs(Path(__file__).resolve().parents[2])
