"""
部署前的环境检查：配置能否读取、生产配置要求、数据库连通与迁移版本、
大模型配置、磁盘剩余空间。只读取和连接，不修改任何数据。
用法：uv run python -m deploy.check_env；有问题时逐条列出并返回非零。
"""

import asyncio
import shutil
import sys

from pydantic import ValidationError

from app.setup.catalog import MODULES
from shared.config.settings import Settings, check_production
from shared.db.database import Database
from shared.db.schema import current_revision, head_revision
from shared.modules.catalog import Catalog

MIN_FREE_GB = 2.0


# 检查数据库能否连通，结构版本是否与代码一致。
async def check_database(settings: Settings) -> list[str]:
    database = Database(settings.database_url, wait_seconds=5)
    try:
        await database.ping()
        current, head = await current_revision(database), head_revision()
    except Exception as error:
        return [f"无法连接数据库：{type(error).__name__}"]
    finally:
        await database.close()
    if current != head:
        shown = current or "未迁移"
        return [f"数据库结构版本是“{shown}”，代码需要“{head}”：请执行 uv run alembic upgrade head"]
    return []


# 检查声明了提示词的模块是否配置了大模型服务。
def check_model(settings: Settings) -> list[str]:
    prompts = Catalog(MODULES).prompts()
    if prompts and not settings.has_model():
        names = "APP_MODEL_BASE_URL、APP_MODEL_NAME、APP_MODEL_API_KEY"
        text = f"有 {len(prompts)} 个提示词，但没有配置 {names}"
        return [text + ("" if settings.env != "production" else "；生产环境会拒绝启动")]
    return []


# 检查磁盘剩余空间。
def check_disk() -> list[str]:
    free = shutil.disk_usage(".").free / 1024**3
    return [] if free >= MIN_FREE_GB else [f"磁盘剩余 {free:.1f} GB，少于 {MIN_FREE_GB} GB"]


# 依次运行全部检查并输出结果。
def main() -> None:
    problems = []
    try:
        settings = Settings()
    except ValidationError as error:
        print(f"配置无法读取：\n{error}")
        sys.exit(1)
    problems += check_production(settings)
    problems += check_model(settings)
    problems += asyncio.run(check_database(settings))
    problems += check_disk()
    kind = settings.database_url.split("://")[0]
    print(f"环境：{settings.env}；数据库：{kind}；代码版本：{settings.code_version}")
    for problem in problems:
        print(f"  - {problem}")
    print("检查通过" if not problems else f"发现 {len(problems)} 个问题")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
