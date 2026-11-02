import argparse
import subprocess
import sys
from pathlib import Path

from fastapi_check.job_model import explore
from fastapi_check.job_model_sources import require_mapping
from fastapi_check.job_tla import REGRESSION, verify_tlc
from fastapi_check.quality.rules import ROOT


def verify_python() -> None:
    require_mapping()
    count, failure = explore(fenced=True)
    if failure:
        raise ValueError("发现违反任务提交规则的执行顺序：" + " → ".join(failure))
    _, mutation = explore(fenced=False)
    if not mutation:
        raise ValueError("检查器未能发现错误模型中的问题：该模型移除了执行次数编号校验")
    print(
        f"限定范围内的状态检查通过：{count} 个状态；2 个 worker、1 个可重试任务、最多执行 2 次",
        flush=True,
    )
    print("错误模型中会出错的执行顺序：" + " → ".join(mutation), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="核对任务接管与提交的有限状态及真实回滚行为")
    parser.add_argument("--jar", type=Path, help="额外使用固定摘要的本地 tla2tools 1.7.4 JAR")
    args = parser.parse_args()
    try:
        if args.jar:
            verify_tlc(args.jar)
            print("TLC 正常模型、指定错误模型反例与真实实现回滚检查通过")
            return
        verify_python()
        result = subprocess.run([sys.executable, "-m", "pytest", "-q", REGRESSION], cwd=ROOT)
        require_mapping()
        raise SystemExit(result.returncode)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
