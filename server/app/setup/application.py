"""
加载产品声明，不创建服务或读取部署环境；各类入口共享相同的组装对象。
"""

from pathlib import Path

from shared.application.spec import ApplicationSpec
from shared.errors.framework import ConfigError
from shared.modules.libraries import LibrarySpec, library_specs
from shared.modules.module import Module


# 导入只发生在请求组装时，框架公共包不反向依赖产品。
def application() -> ApplicationSpec:
    from app.product import APPLICATION

    if not isinstance(APPLICATION, ApplicationSpec):
        raise ConfigError(["app.product.APPLICATION必须是ApplicationSpec"])
    APPLICATION.validate()
    return APPLICATION


# 静态工具读取同一份模块声明，不建立服务或连接。
def application_modules() -> tuple[Module, ...]:
    from app.setup.catalog import MODULES

    declared = application().modules
    return tuple(MODULES) if declared is None else declared


# 工具声明也属于实际产品结构，读取不会创建网络或数据库资源。
def application_libraries() -> list[LibrarySpec]:
    return library_specs(Path(__file__).resolve().parents[2])
