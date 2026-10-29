import argparse
import json
import subprocess
import sys
from pathlib import Path

from fastapi_check.matrix import clean_environment
from fastapi_check.quality.rules import PROJECT
from fastapi_project.development.check_storage import export_record
from fastapi_project.development.integration_git import integrate, save_report
from fastapi_project.development.integration_resolve import resolve

WORKER = (
    "from pathlib import Path; from fastapi_dev.main import bootstrap; "
    "bootstrap(Path.cwd().parent); import runpy; "
    "runpy.run_module('fastapi_project.integration_worker',run_name='__main__')"
)


def validation(project: Path, tree: Path, postgres: str, *, workers: int = 4) -> dict:
    if not 0 <= workers <= 32:
        raise ValueError("整合检查进程预算应为0至32")
    env = clean_environment() | {
        "FASTAPI_MERGE_POSTGRES": postgres,
        "FASTAPI_MERGE_WORKERS": str(workers),
    }
    log = tree.parent / "worker.log"
    with log.open("w") as output:
        result = subprocess.run(
            [sys.executable, "-c", WORKER],
            cwd=tree / "server",
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
            timeout=600,
        )
    if result.returncode:
        diagnostic = tree / ".agents/records/migration-structure-diff.json"
        if diagnostic.is_file():
            (tree.parent / "migration-structure-diff.json").write_bytes(diagnostic.read_bytes())
        path = tree / ".agents/records/integration-stage.json"
        stage = json.loads(path.read_text())["stage"] if path.is_file() else "worker-start"
        return {"passed": False, "stage": stage, "log": str(log)}
    data = json.loads((tree / ".agents/records/integration-result.json").read_text())
    source = tree / "server/var/development/checks" / (data["check"] + ".json")
    destination = project / "server/var/development/checks"
    if (destination / source.name).exists():
        raise ValueError("检查编号已存在，请重新整合，不能覆盖原证据")
    export_record(source, destination)
    return data | {
        "log": str(log),
        "exported_check": "server/var/development/checks/" + source.name,
    }


def refresh(project: Path, report: dict) -> None:
    if not report["applied"]:
        return
    result = subprocess.run(
        [sys.executable, "-c", "from fastapi_dev.main import main; main()", "panel"],
        cwd=project / "server",
        env=clean_environment(),
        capture_output=True,
        check=False,
    )
    if result.returncode:
        report["panel_error"] = "源码已经应用，但面板刷新失败，请运行dev panel核对原件"
    else:
        report["panel"] = "out/panel/index.html"
    save_report(project, report)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("branch")
    parser.add_argument("--postgres", required=True)
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    report = integrate(
        PROJECT,
        args.branch,
        lambda tree: validation(PROJECT, tree, args.postgres),
        resolve,
        preview=args.preview,
    )
    refresh(PROJECT, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report.get("error") or report.get("panel_error"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
