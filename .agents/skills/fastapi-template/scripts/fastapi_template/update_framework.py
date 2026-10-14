"""
为已经开发的项目接收模板增量更新，不要求它与模板具有共同 Git 历史。
默认只预览，--apply 才保存；任何冲突阻止全部写入。业务模块与迁移历史不参与更新。
"""

import argparse
import json

from fastapi_check.quality.rules import PROJECT
from fastapi_template.template.files import check_base, manifest
from fastapi_template.template.merge import apply_plan, update_plan


# 明确旧版本与新版本目录；项目自身不必有模板远程或共同祖先。
def main() -> None:
    from pathlib import Path

    parser = argparse.ArgumentParser(description="预览或接收框架增量更新")
    parser.add_argument("--base", required=True, type=Path, help="项目上次采用的模板版本目录")
    parser.add_argument("--source", required=True, type=Path, help="准备升级到的模板版本目录")
    parser.add_argument(
        "--target", type=Path, default=PROJECT, help="产品目录；旧产品可从新版工具明确指定"
    )
    parser.add_argument("--recovery-proof", type=Path, help="产品自己的外部回收证明JSON，可选")
    parser.add_argument("--apply", action="store_true", help="没有冲突时保存全部框架变化")
    args = parser.parse_args()
    base, source = args.base.resolve(), args.source.resolve()
    target = args.target.resolve()
    if not (target / "server").is_dir() or target in (base, source):
        parser.error("产品目录必须存在，并与旧模板、新模板目录不同")
    for root in (base, source):
        if not (root / "server/framework.lock").is_file():
            parser.error(f"不是模板版本目录：{root}")
    changes, manual = update_plan(target, base, source, recovery_proof=args.recovery_proof)
    print(
        json.dumps(
            {
                "changes": [{"file": change.name, "state": change.state} for change in changes],
                "newly_managed": check_base(target, base, manifest(source)),
                "manual_review": manual,
                "conflicts": sum(change.state == "conflict" for change in changes),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if any(change.state == "conflict" for change in changes):
        parser.exit(1, "存在冲突，所有文件保持原样。请先人工处理冲突后重新预览。\n")
    if args.apply:
        apply_plan(target, base, source, changes, recovery_proof=args.recovery_proof)
        print(
            "框架文件已更新。请审查依赖与配置变化，更新 framework.lock，"
            "生成文档并运行完整检查；数据库尚未变更。"
        )


if __name__ == "__main__":
    main()
