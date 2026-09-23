"""
验证注册约束和受限调用入口。
未登记的模块、操作及调用方不能通过入口执行。
"""

import pytest

from service.notes import rules
from shared.modules.registry import Module, Registry
from shared.monitor.trace import Monitor


# 创建只有入口和校验规则的独立注册表。
def registry() -> Registry:
    return Registry(
        (
            Module("api", "1", "", (), ("rules",), entry=True),
            Module("rules", "1", "", ("clean",)),
        ),
        Monitor(),
    )


# 验证正常调用、记录及未公开方法。
def test_port() -> None:
    catalog = registry()
    port = catalog.bind("api", "rules", rules)
    assert port.clean(" 标题 ", "") == "标题"
    assert catalog.monitor.snapshot()["items"][0]["status"] == "ok"
    with pytest.raises(AttributeError):
        port.hidden()
    with pytest.raises(ValueError):
        catalog.bind("rules", "api", rules)


# 验证非法注册在组装时立即失败。
@pytest.mark.parametrize(
    "modules",
    [
        (Module("same", "1", "", ()), Module("same", "1", "", ())),
        (Module("api", "1", "", (), ("missing",)),),
        (Module("api", "1", "", (), ("api",)),),
        (Module("api", "1", "", ("run", "run")),),
    ],
)
def test_invalid_registration(modules: tuple[Module, ...]) -> None:
    with pytest.raises(ValueError):
        Registry(modules, Monitor())


# 验证内部模块入口无法直接作为外部入口使用。
def test_caller() -> None:
    catalog = Registry(
        (
            Module("service", "1", "", (), ("rules",)),
            Module("rules", "1", "", ("clean",)),
        ),
        Monitor(),
    )
    port = catalog.bind("service", "rules", rules)
    with pytest.raises(PermissionError):
        port.clean("标题", "")


# 验证底层调用入口也不能绕过已登记的依赖关系。
def test_direct_call_checks_edge() -> None:
    catalog = registry()
    with pytest.raises(PermissionError):
        catalog.call("api", "api", rules, "clean", "标题", "")
