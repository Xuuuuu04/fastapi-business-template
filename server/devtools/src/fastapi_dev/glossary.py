"""
业务词表命令，只保存显式定义和操作归属，不读数据库或原始材料。
"""

import argparse

from fastapi_check.quality.rules import PROJECT
from fastapi_project.development.glossary import BusinessTerm, add_term, read_glossary


# 每次登记都验证词义和别名唯一，空项目show仍保持无业务词。
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("show")
    add = actions.add_parser("add")
    add.add_argument("word")
    add.add_argument("--definition", required=True)
    add.add_argument("--module", required=True)
    add.add_argument("--alias", action="append", default=[])
    add.add_argument("--operation", action="append", required=True)
    args = parser.parse_args()
    if args.action == "add":
        add_term(
            PROJECT,
            BusinessTerm(
                word=args.word,
                definition=args.definition,
                module=args.module,
                aliases=args.alias,
                operations=args.operation,
            ),
        )
    print(read_glossary(PROJECT).model_dump_json(indent=2))


if __name__ == "__main__":
    main()
