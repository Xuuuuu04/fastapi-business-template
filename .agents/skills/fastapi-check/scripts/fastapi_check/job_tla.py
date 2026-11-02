import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi_check.job_model_sources import require_mapping
from fastapi_check.quality.rules import PROJECT, ROOT

ASSETS = PROJECT / ".agents/skills/fastapi-check/assets"
INPUTS = (
    "JobCommit.tla",
    "JobCommit.cfg",
    "JobCommitBroken.cfg",
    "job_model.json",
    "job_tlc_tool.json",
)
REGRESSION = (
    "tests/framework/test_job_commit.py::test_takeover_after_precheck_rolls_back_old_commit"
)


def input_hashes() -> dict[str, str]:
    return {name: hashlib.sha256((ASSETS / name).read_bytes()).hexdigest() for name in INPUTS}


def check_tool(jar: Path) -> str:
    tool = json.loads((ASSETS / "job_tlc_tool.json").read_text(encoding="utf-8"))
    actual = hashlib.sha256(jar.read_bytes()).hexdigest()
    if actual != tool["sha256"]:
        raise ValueError("TLC 工具摘要不符，需要固定版本 " + str(tool["version"]))
    return str(tool["version"])


def checked_output(result: subprocess.CompletedProcess[str], broken: bool) -> str | None:
    text = result.stdout + result.stderr
    passed = (
        result.returncode == 12 and "Invariant CurrentAttemptOnly is violated." in text
        if broken
        else result.returncode == 0 and "Model checking completed. No error has been found." in text
    )
    if not passed:
        stage = "故意错误模型没有产生指定的旧尝试提交反例" if broken else "任务状态模型未通过"
        raise ValueError(stage + "，请查看本轮日志")
    count = re.search(r"([\d,]+) distinct states found", text)
    return count[1].replace(",", "") if count else None


def run_tlc(jar: Path, output: Path, broken: bool) -> str | None:
    label = "mutation" if broken else "model"
    command = [
        "java",
        "-XX:+UseParallelGC",
        "-Xmx512m",
        "-cp",
        str(jar),
        "tlc2.TLC",
        "-workers",
        "1",
        "-metadir",
        str(output / f"{label}-states"),
        "-config",
        str(ASSETS / ("JobCommitBroken.cfg" if broken else "JobCommit.cfg")),
        str(ASSETS / "JobCommit.tla"),
    ]
    try:
        result = subprocess.run(
            command, cwd=ROOT, capture_output=True, check=False, text=True, timeout=60
        )
    except subprocess.TimeoutExpired as error:
        captured = error.stdout or b""
        text = captured.decode(errors="replace") if isinstance(captured, bytes) else captured
        (output / f"{label}.log").write_text(text, encoding="utf-8")
        raise ValueError("TLC 超过 60 秒，已停止本轮检查") from error
    (output / f"{label}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    return checked_output(result, broken)


def run_implementation(output: Path) -> None:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", REGRESSION],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as error:
        captured = error.stdout or b""
        text = captured.decode(errors="replace") if isinstance(captured, bytes) else captured
        (output / "implementation.log").write_text(text, encoding="utf-8")
        raise ValueError("真实回滚检查超过 120 秒，已停止本轮检查") from error
    (output / "implementation.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise ValueError("真实旧尝试提交回滚测试未通过，请查看 implementation.log")


def verify_tlc(jar: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8]
    output = ROOT / "var/formal" / stamp
    output.mkdir(parents=True)
    summary: dict[str, object] = {
        "scope": "1 个可重试普通任务、2 个 worker、最多 2 次尝试；旧尝试不能提交，最终最多提交一次",
        "checked_at": datetime.now(UTC).isoformat(),
        "status": "本轮尚未通过",
        "tool": "未核对",
        "states": None,
        "mutation_states": None,
        "implementation": "未执行",
        "inputs": {},
        "error": None,
    }
    try:
        require_mapping()
        inputs = input_hashes()
        summary["inputs"] = inputs
        summary["tool"] = check_tool(jar.resolve())
        summary["states"] = run_tlc(jar.resolve(), output, False)
        summary["mutation_states"] = run_tlc(jar.resolve(), output, True)
        summary["implementation"] = "进行中"
        run_implementation(output)
        summary["implementation"] = "通过"
        require_mapping()
        if input_hashes() != inputs:
            raise ValueError("检查期间状态模型或映射发生变化，请重新检查")
        summary["status"] = "通过"
        return output
    except BaseException as error:
        if summary["implementation"] == "进行中":
            summary["implementation"] = "失败"
        summary["status"] = "失败"
        summary["error"] = str(error)
        raise
    finally:
        (output / "result.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"本轮形式化检查结果：{output}", flush=True)
