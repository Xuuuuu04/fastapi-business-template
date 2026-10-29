import argparse
import json
import sys

from fastapi_check.quality.rules import PROJECT
from fastapi_project.development.evidence_retention import collect, pin


def main() -> None:
    parser = argparse.ArgumentParser()
    if sys.argv[0].endswith("pin"):
        parser.add_argument("identity")
        parser.add_argument("--reason", default="")
        parser.add_argument("--remove", action="store_true")
        args = parser.parse_args()
        result = pin(PROJECT, args.identity, args.reason, remove=args.remove)
    else:
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--preview-id")
        args = parser.parse_args()
        if args.apply != bool(args.preview_id):
            parser.error("应用清理必须一起提供--apply和--preview-id")
        result = collect(PROJECT, args.preview_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
