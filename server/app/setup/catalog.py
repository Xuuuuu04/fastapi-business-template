"""
模块总目录：列出启用哪些业务模块。这是全项目唯一需要登记模块的地方。
新增模块用 `uv run python -m tools.new_module` 生成，它会自动加到这里；
关闭模块就从这里删掉，依赖它的其他模块会在启动检查时报错，不会静默跳过。
BACKENDS 登记项目自己的基础设施实现（文件存储、缓存、大模型服务商），写法见 app/setup/backends.py。
"""

from app.setup.backends import Backend
from service.file_library.module import module as file_library
from service.order_quote.module import module as order_quote
from service.product_catalog.module import module as product_catalog
from service.user_access.module import module as user_access
from shared.modules.module import Module

MODULES: list[Module] = [
    product_catalog,
    order_quote,
    user_access,
    file_library,
]

BACKENDS: list[Backend] = []
