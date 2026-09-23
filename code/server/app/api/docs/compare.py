"""
比较两份 OpenAPI 的接口和数据模型变化。
报告用于人工审查，不自动断言接口兼容。
"""

import argparse
import json
from pathlib import Path

from app.api.docs.export import METHODS


# 将接口按方法与路径整理成稳定的索引。
def operations(schema: dict) -> dict:
    return {
        f"{method.upper()} {path}": item
        for path, entries in schema.get("paths", {}).items()
        for method, item in entries.items()
        if method in METHODS
    }


# 列出接口增删、声明修改和共享模型变化。
def compare(before: dict, after: dict) -> list[str]:
    old, new = operations(before), operations(after)
    changes = []
    for key in sorted(old.keys() - new.keys()):
        changes.append(f"删除接口：{key}")
    for key in sorted(new.keys() - old.keys()):
        changes.append(f"新增接口：{key}")
    for key in sorted(old.keys() & new.keys()):
        if old[key] != new[key]:
            changes.append(f"接口声明变化：{key}")
    if before.get("components") != after.get("components"):
        changes.append("共享模型或权限定义变化：请检查 components")
    if before.get("security") != after.get("security"):
        changes.append("全局权限变化：请检查 security")
    return changes


# 读取前后版本并输出待审查的变化。
def main() -> None:
    parser = argparse.ArgumentParser(description="比较 API 文档")
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    args = parser.parse_args()
    before = json.loads(args.before.read_text(encoding="utf-8"))
    after = json.loads(args.after.read_text(encoding="utf-8"))
    print("\n".join(compare(before, after)) or "未发现接口声明变化。")


if __name__ == "__main__":
    main()
