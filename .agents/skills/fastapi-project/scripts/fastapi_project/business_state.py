"""
生成或检查本机业务现状，默认不访问数据库；--runs明确读取当前数据库，生成区外手写内容保留。
"""

import argparse
import asyncio

from fastapi_check.quality.rules import PROJECT
from fastapi_project.development.business_runtime import observe
from fastapi_project.development.business_state import database_identity, outdated, update

from app.setup.application import application, application_modules
from app.setup.operations import with_operations
from shared.config.settings import Settings
from shared.db.database import Database
from shared.modules.catalog import Catalog


# 查询失败不写新状态、不打印连接目标或凭据。
async def runtime(settings: Settings, catalog: Catalog) -> dict:
    database = Database(settings.database_url)
    try:
        return await observe(database, catalog)
    finally:
        await database.close()


# 开工先读、收工显式刷新；检查绝不自动把过期运行证据更新成成功。
def main() -> None:
    parser = argparse.ArgumentParser(description="生成业务现状（生成事实/手写判断分开）")
    parser.add_argument("--module", action="append", default=[])
    parser.add_argument("--runs", action="store_true", help="明确读取当前配置数据库的真实运行状态")
    parser.add_argument("--check", action="store_true", help="只检查版本/声明/生成时刻是否过期")
    args = parser.parse_args()
    if args.check and args.runs:
        parser.error("--check不读取数据库，不与--runs同时使用")
    settings = application().settings("runtime" if args.runs else "offline")
    catalog = Catalog(with_operations(settings, application_modules()))
    missing = set(args.module) - catalog.modules.keys()
    if missing:
        raise SystemExit("未登记模块：" + ",".join(sorted(missing)))
    if args.check:
        paths = outdated(
            catalog,
            PROJECT,
            set(settings.disabled_modules),
            database_id=database_identity(settings.database_url),
        )
        if args.module:
            paths = [path for path in paths if path.stem in args.module]
        for path in paths:
            print("业务现状生成部分过期：" + str(path.relative_to(PROJECT)))
        raise SystemExit(1 if paths else 0)
    facts = None
    if args.runs:
        print("明确读取当前APP_DATABASE_URL指向数据库；输出不包含连接目标或凭据。")
        try:
            facts = asyncio.run(runtime(settings, catalog))
        except Exception as error:
            raise SystemExit("业务现状读取失败：" + type(error).__name__) from None
    paths = update(catalog, PROJECT, set(settings.disabled_modules), facts, args.module or None)
    for path in paths:
        print("已生成：" + str(path.relative_to(PROJECT)))
    if not paths:
        print("当前没有业务模块或开启的内置运维；无需生成业务现状。")


if __name__ == "__main__":
    main()
