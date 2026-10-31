import argparse
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class RunCase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    operation: str = Field(min_length=1)
    input: dict[str, JsonValue] = Field(default_factory=dict)
    org: str = "*"
    permissions: list[str] = Field(default_factory=lambda: ["*"])
    expected: dict[str, JsonValue] | None = None


def arguments() -> tuple[RunCase, bool]:
    parser = argparse.ArgumentParser(description="用本地配置运行操作或复用 JSON 业务样例")
    parser.add_argument("operation", nargs="?", help="登记的操作名")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--case", type=Path, help="业务样例 JSON，包含 operation/input/expected")
    source.add_argument("--input", help="输入 JSON")
    source.add_argument("--input-file", type=Path, help="输入 JSON 文件")
    parser.add_argument("--org", help="运行所属组织")
    parser.add_argument("--allow-write", action="store_true", help="明确允许本次 command 操作写入")
    args = parser.parse_args()
    if args.case and (args.operation or args.org):
        parser.error("--case 不能和 operation 或 --org 混用，请在样例中配置")
    if not args.case and not args.operation:
        parser.error("需要操作名或 --case")
    try:
        if args.case:
            case = RunCase.model_validate_json(args.case.read_text(encoding="utf-8"))
        else:
            text = args.input_file.read_text(encoding="utf-8") if args.input_file else args.input
            case = RunCase(
                operation=args.operation,
                input=json.loads("{}" if text is None else text),
                org=args.org or "*",
            )
    except (OSError, ValueError) as error:
        parser.error(f"样例或输入无法读取：{type(error).__name__}，请检查路径、JSON 和字段")
    return case, args.allow_write
