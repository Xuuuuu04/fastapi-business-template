"""
生成纯工具包，不登记HTTP、数据库或任务入口；预览不写文件。
"""

import argparse
import json
import re
from pathlib import Path

from fastapi_check.quality.rules import ROOT


# 名称与标题明确，工具不能和已有业务包同名。
def library_files(name: str, title: str, root: Path = ROOT) -> dict[Path, str]:
    if not re.fullmatch(r"[a-z][a-z0-9]*(_[a-z0-9]+)+", name):
        raise ValueError("工具包名称应为至少两个英文词")
    if not title.strip() or "\n" in title or '"""' in title:
        raise ValueError("工具包标题必须为单行用途")
    if (root / "library" / name).exists() or (root / "service" / name).exists():
        raise ValueError("工具包或同名业务包已经存在")
    folder = root / "library" / name
    header = '"""\n' + title + '\n"""\n\n'
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
        folder
        / "README.md": f"# {title}\n\n纯文本整理，不访问外部资源。公开导出：normalize_text。\n",
        folder / "public.py": header
        + f'from library.{name}.calc.texts import normalize_text\n\n__all__ = ["normalize_text"]\n',
        folder / "calc/README.md": "# 纯计算\n\n只接收参数并返回结果，不读取外部状态。\n",
        folder / "calc/texts.py": header
        + "# 整理文本首尾空白。\ndef normalize_text(value: str) -> str:\n"
        + "    return value.strip()\n",
        root / "tests/unit" / f"test_{name}.py": header
        + f"from library.{name}.public import normalize_text\n\n\n"
        + "# 正常与空输入都可重复验证。\ndef test_normalize_text() -> None:\n"
        + '    assert normalize_text("  sample  ") == "sample"\n'
        + '    assert normalize_text("") == ""\n',
    }


# 完整文件清单先验证，预览只输出相对位置。
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
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
