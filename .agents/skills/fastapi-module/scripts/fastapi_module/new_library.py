import argparse
import json
import re
from pathlib import Path

from fastapi_check.quality.rules import ROOT


def library_files(name: str, title: str, root: Path = ROOT) -> dict[Path, str]:
    if not re.fullmatch(r"[a-z][a-z0-9]*(_[a-z0-9]+)+", name):
        raise ValueError("工具包名称应为至少两个英文词")
    if not title.strip() or "\n" in title:
        raise ValueError("工具包标题必须为单行用途")
    if (root / "library" / name).exists() or (root / "service" / name).exists():
        raise ValueError("工具包或同名业务包已经存在")
    folder = root / "library" / name
    return {
        folder / "module.json": json.dumps(
            dict(
                schema_version=2,
                kind="library",
                name=name,
                title=title,
                exports=["normalize_text"],
                aliases=[],
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        folder / "public.py": f"from library.{name}.calc.texts import normalize_text\n\n"
        + '__all__ = ["normalize_text"]\n',
        folder / "calc/texts.py": "def normalize_text(value: str) -> str:\n"
        + "    return value.strip()\n",
        root
        / "tests/unit"
        / f"test_{name}.py": f"from library.{name}.public import normalize_text\n\n\n"
        + "def test_normalize_text() -> None:\n"
        + '    assert normalize_text("  sample  ") == "sample"\n'
        + '    assert normalize_text("") == ""\n',
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("--title", required=True)
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    files = library_files(args.name, args.title)
    if not args.preview:
        for path, text in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    print(
        json.dumps(
            {
                "preview": args.preview,
                "files": [str(path.relative_to(ROOT.parent)) for path in files],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
