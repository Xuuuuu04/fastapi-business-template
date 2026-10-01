"""
全量检查，一条命令跑完每次提交前必须通过的全部检查：
代码风格与格式（ruff）、类型检查（mypy）、生成文档是否过期、默认测试（含架构、质量、安全、恢复测试）。
用法：uv run python -m tools.check；加 --postgres 地址，会在 PostgreSQL 上再跑一遍测试。
压力测试和浏览器测试不在这里，见 tests/load 和 tests/browser。
"""

import argparse
import os
import subprocess
import sys

from tools.quality.rules import ROOT

TYPED = ("app", "service", "shared", "tools", "deploy")


# 列出全部检查；类型检查只包含有 Python 文件的目录（未添加业务时 service 可能暂时为空）。
def steps(module: str = "") -> list[tuple[str, list[str]]]:
    typed = [name for name in TYPED if any((ROOT / name).rglob("*.py"))]
    tests = ["-m", "pytest", "-q"]
    if module:
        tests += [f"tests/modules/{module}", f"tests/integration/{module}"]
    return [
        ("代码风格", ["ruff", "check", "."]),
        ("代码格式", ["ruff", "format", "--check", "."]),
        ("类型检查", ["mypy", *typed]),
        ("生成文档", ["-m", "tools.export_docs", "--check"]),
        ("模块测试" if module else "默认测试", tests),
    ]


# 运行一项检查，返回是否通过。
def run(title: str, command: list[str], env: dict[str, str]) -> bool:
    runner = [sys.executable, "-m", *command] if command[0] != "-m" else [sys.executable, *command]
    print(f"\n==> {title}：{' '.join(command)}", flush=True)
    return subprocess.run(runner, cwd=ROOT, env=env, check=False).returncode == 0


# 依次运行全部检查并汇总结果。
def main() -> None:
    parser = argparse.ArgumentParser(description="运行全部必需检查")
    parser.add_argument(
        "--module", default="", help="只跑指定模块的步骤与接口测试，其余代码检查保持完整"
    )
    parser.add_argument(
        "--postgres", default="", help="PostgreSQL 连接地址，用于在真实数据库上再跑测试"
    )
    args = parser.parse_args()
    if args.module:
        from app.setup.catalog import MODULES

        if args.module not in {module.name for module in MODULES}:
            parser.error(f"模块没有登记：{args.module}")
        for group in ("modules", "integration"):
            if not list((ROOT / "tests" / group / args.module).glob("test_*.py")):
                parser.error(f"模块缺少 tests/{group}/{args.module}/test_*.py")
    env = dict(os.environ)
    selected = steps(args.module)
    results = [(title, run(title, command, env)) for title, command in selected]
    if args.postgres:
        env["APP_TEST_DATABASE_URL"] = args.postgres
        results.append(("PostgreSQL 测试", run("PostgreSQL 测试", selected[-1][1], env)))
    print("\n检查结果：")
    for title, passed in results:
        print(f"  {'通过' if passed else '失败'}  {title}")
    if not args.postgres:
        print("  未运行  PostgreSQL 测试（生产使用 PostgreSQL 时，发布前必须加 --postgres 运行）")
    sys.exit(0 if all(passed for _, passed in results) else 1)


if __name__ == "__main__":
    main()
