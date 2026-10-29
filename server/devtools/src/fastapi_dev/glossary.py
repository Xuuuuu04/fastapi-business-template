import argparse

from fastapi_check.quality.rules import PROJECT
from fastapi_project.development.glossary import BusinessTerm, add_term, read_glossary


def main() -> None:
    parser = argparse.ArgumentParser()
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
