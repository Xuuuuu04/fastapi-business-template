import os
import runpy
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[4]
PACKAGES = sorted((PROJECT / ".agents/skills").glob("fastapi-*/scripts"))
sys.path[:0] = [str(PROJECT / "server"), *map(str, PACKAGES)]
os.chdir(PROJECT / "server")
COMMANDS = ["diagnose", "jobs", "pipelines", "drill", "make_key"]
if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
    raise SystemExit("用法：python run_operations.py {" + ",".join(COMMANDS) + "} [参数]")
command = sys.argv.pop(1)
runpy.run_module("fastapi_operations." + command, run_name="__main__")
