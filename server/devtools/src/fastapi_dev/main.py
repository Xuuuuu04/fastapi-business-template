import argparse
import json
import os
import runpy
import sys
from pathlib import Path

COMMANDS = {
    "new-library": "fastapi_module.new_library",
    "check": "fastapi_check.check",
    "verify-model": "fastapi_check.verify_model",
    "acceptance-server": "fastapi_check.acceptance_server",
    "run": "fastapi_check.run_operation",
    "locate": "fastapi_business.locate",
    "docs": "fastapi_check.openapi",
    "diagnose": "fastapi_operations.diagnose",
    "jobs": "fastapi_operations.jobs",
    "pipelines": "fastapi_operations.pipelines",
    "make-key": "fastapi_operations.make_key",
    "deploy": "fastapi_operations.deploy",
    "new-module": "fastapi_module.new_module",
    "new-operation": "fastapi_module.new_operation",
    "new-pipeline": "fastapi_module.new_pipeline",
    "new-project": "fastapi_template.start_project",
    "upgrade": "fastapi_template.update_framework",
    "compare-api": "fastapi_template.compare_api",
}


def project_root() -> Path:
    for root in (Path.cwd(), *Path.cwd().parents, *Path(__file__).resolve().parents):
        if (root / "server/pyproject.toml").is_file() and (root / ".agents/skills").is_dir():
            return root
    raise SystemExit("找不到产品目录，请在产品根目录或 server 目录执行 dev")


def bootstrap(root: Path) -> None:
    folders = sorted((root / ".agents/skills").glob("*/scripts"))
    sys.path[:0] = [str(root / "server"), *map(str, folders)]
    os.chdir(root / "server")


def inspect_application() -> None:
    from app.setup.application import application, application_libraries, application_modules

    description = application().describe()
    description["modules"] = [item.name for item in application_modules()]
    description["libraries"] = [item.shape() for item in application_libraries()]
    print(json.dumps(description, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["inspect", *COMMANDS])
    arguments = parser.parse_args(sys.argv[1:2])
    remaining = sys.argv[2:]
    bootstrap(project_root())
    if arguments.command == "inspect":
        if remaining:
            parser.error("inspect 不接受额外参数")
        inspect_application()
        return
    sys.argv = ["dev " + arguments.command, *remaining]
    runpy.run_module(COMMANDS[arguments.command], run_name="__main__")


if __name__ == "__main__":
    main()
