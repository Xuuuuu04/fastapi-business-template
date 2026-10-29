import argparse
import json

from fastapi_business.search import locate
from fastapi_check.quality.rules import PROJECT

from app.setup.application import application_modules
from shared.modules.catalog import Catalog


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    if not args.query.strip() or not 1 <= args.limit <= 100:
        parser.error("query 不能为空，limit 必须在 1 到 100 之间")
    from fastapi_business.routes import local_routes

    result = locate(Catalog(application_modules()), PROJECT, args.query, args.limit, local_routes())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
