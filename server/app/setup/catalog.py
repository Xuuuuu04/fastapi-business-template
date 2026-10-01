"""
模块总目录：登记项目包含哪些业务模块。这是全项目唯一需要登记模块的地方。
新增模块用 `uv run python -m tools.new_module` 生成，它会自动加到这里；
关闭模块使用 APP_DISABLED_MODULES；依赖它的其他模块会在启动检查时报错。
"""

from service.file_library.module import module as file_library
from service.user_access.module import module as user_access
from shared.modules.module import Module

MODULES: list[Module] = [
    user_access,
    file_library,
]
