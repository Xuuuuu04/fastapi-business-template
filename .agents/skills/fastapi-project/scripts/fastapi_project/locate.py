"""
按业务词定位本地声明，只读，不启动服务、不访问数据库。
"""

import argparse
import json
from pathlib import Path

from fastapi_project.development.locate import locate

from app.setup.catalog import MODULES
from shared.modules.catalog import Catalog


# 命令结果有界；明细中保留继续查看的准确命令。
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.query.strip() or not 1 <= args.limit <= 100:
        parser.error("query 不能为空，limit 必须在 1 到 100 之间")
    from fastapi_project.development.locate_routes import local_routes

    project = Path(__file__).resolve().parents[5]
    result = locate(Catalog(MODULES), project, args.query, args.limit, local_routes())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
