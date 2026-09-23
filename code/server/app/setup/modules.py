"""
集中登记单体内受管理的业务模块及允许的调用关系。
新增业务必须显式登记，基础框架能力不作为业务插件重复注册。
"""

from shared.modules.registry import Module

MODULES = (
    Module(
        name="notes_api",
        version="1",
        source="app/api/routes/notes/routes.py",
        actions=(),
        calls=("notes",),
        entry=True,
    ),
    Module(
        name="notes",
        version="1",
        source="service/notes/service.py",
        actions=("list", "get", "create", "update", "delete"),
        calls=("note_store", "note_rules"),
    ),
    Module(
        name="note_store",
        version="1",
        source="service/notes/store/sqlite.py",
        actions=("transaction", "list", "get", "create", "update", "delete"),
        scopes=("transaction",),
    ),
    Module(
        name="note_rules",
        version="1",
        source="service/notes/rules.py",
        actions=("clean",),
    ),
)
