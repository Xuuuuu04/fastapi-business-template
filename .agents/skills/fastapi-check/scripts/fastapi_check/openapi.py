import argparse
import json
import sys

from fastapi_check.quality.rules import PROJECT

from app.setup.application import application
from app.setup.web import create_app

OPENAPI = PROJECT / "doc" / "api" / "openapi.json"


def openapi_text() -> str:
    app = create_app(application().settings("offline", docs=True))
    return json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="只检查 openapi.json 是否过期，不写入")
    arguments = parser.parse_args()
    text = openapi_text()
    name = OPENAPI.relative_to(PROJECT)
    if arguments.check:
        if not OPENAPI.exists() or OPENAPI.read_text(encoding="utf-8") != text:
            print(f"接口文档已过期：{name}")
            sys.exit(1)
        return
    OPENAPI.parent.mkdir(parents=True, exist_ok=True)
    OPENAPI.write_text(text, encoding="utf-8")
    print(f"已生成 {name}")


if __name__ == "__main__":
    main()
