"""
比较两份 OpenAPI 描述，列出接口的增加、删除和声明变化，供人判断是否需要新版本接口。
用法：uv run python -m tools.compare_api --before 旧/openapi.json --after ../doc/api/openapi.json
报告只提示变化，兼容性由开发者判断。
"""

import argparse
import json
from pathlib import Path
from typing import Any

from tools.api_doc import METHODS


# 把接口按“方法 路径”整理成索引。
def operations(schema: dict[str, Any]) -> dict[str, Any]:
    return {
        f"{method.upper()} {path}": item
        for path, entries in schema.get("paths", {}).items()
        for method, item in entries.items()
        if method in METHODS
    }


# 列出接口和数据模型的变化。
def compare(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    old, new = operations(before), operations(after)
    changes = [f"删除接口：{key}" for key in sorted(old.keys() - new.keys())]
    changes += [f"新增接口：{key}" for key in sorted(new.keys() - old.keys())]
    changes += [
        f"接口声明变化：{key}" for key in sorted(old.keys() & new.keys()) if old[key] != new[key]
    ]
    old_models = before.get("components", {}).get("schemas", {})
    new_models = after.get("components", {}).get("schemas", {})
    changes += [f"删除数据模型：{name}" for name in sorted(old_models.keys() - new_models.keys())]
    changes += [
        f"数据模型变化：{name}"
        for name in sorted(old_models.keys() & new_models.keys())
        if old_models[name] != new_models[name]
    ]
    return changes


# 读取前后两份描述并打印变化。
def main() -> None:
    parser = argparse.ArgumentParser(description="比较两份 OpenAPI 描述")
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    args = parser.parse_args()
    before = json.loads(args.before.read_text(encoding="utf-8"))
    after = json.loads(args.after.read_text(encoding="utf-8"))
    print("\n".join(compare(before, after)) or "没有发现接口声明变化。")


if __name__ == "__main__":
    main()
