"""
统一开发入口，从命令所属产品读取声明，生产服务不导入本包。
"""

import argparse
import json
import os
import runpy
import sys
from pathlib import Path

COMMANDS = {
    "pin": "fastapi_project.retention",
    "gc": "fastapi_project.retention",
    "merge": "fastapi_project.integration",
    "panel": "fastapi_project.panel",
    "skeleton": "fastapi_module.skeleton",
    "start": "fastapi_dev.tasks",
    "finish": "fastapi_dev.tasks",
    "ask-contract": "fastapi_dev.tasks",
    "review-pack": "fastapi_dev.tasks",
    "glossary": "fastapi_dev.glossary",
    "rules": "fastapi_dev.rules",
    "plan": "fastapi_dev.plan",
    "new-library": "fastapi_module.new_library",
    "check": "fastapi_check.check",
    "status": "fastapi_project.project",
    "locate": "fastapi_project.locate",
    "impact": "fastapi_project.impact",
    "docs": "fastapi_docs.export_docs",
    "diagnose": "fastapi_operations.diagnose",
    "jobs": "fastapi_operations.jobs",
    "pipelines": "fastapi_operations.pipelines",
    "drill": "fastapi_operations.drill",
    "new-module": "fastapi_module.new_module",
    "new-operation": "fastapi_module.new_operation",
    "new-pipeline": "fastapi_module.new_pipeline",
    "new-project": "fastapi_template.start_project",
    "upgrade": "fastapi_template.update_framework",
    "framework-lock": "fastapi_check.framework_lock",
}


# 当前产品优先，编辑安装的源码位置作为备用，不扫描其他项目或凭据目录。
def project_root() -> Path:
    for root in (Path.cwd(), *Path.cwd().parents, *Path(__file__).resolve().parents):
        if (root / "server/pyproject.toml").is_file() and (root / ".agents/skills").is_dir():
            return root
    raise SystemExit("找不到产品，请在产品或server目录执行dev")


# 已有命令共用一份实现，入口不改变检查、生成或恢复的实际行为。
def bootstrap(root: Path) -> None:
    folders = sorted((root / ".agents/skills").glob("*/scripts"))
    sys.path[:0] = [str(root / "server"), *map(str, folders)]
    os.chdir(root / "server")


# inspect只输出声明，既不创建服务也不读取环境配置。
def inspect_application() -> None:
    from app.setup.application import application, application_libraries, application_modules

    description = application().describe()
    description["modules"] = [item.name for item in application_modules()]
    description["libraries"] = [item.shape() for item in application_libraries()]
    print(json.dumps(description, ensure_ascii=False, indent=2))


# 参数交给所选工具，未知命令在任何生成或数据库操作之前拒绝。
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inspect", *COMMANDS])
    arguments = parser.parse_args(sys.argv[1:2])
    remaining = sys.argv[2:]
    bootstrap(project_root())
    if arguments.command == "inspect":
        if remaining:
            parser.error("inspect没有额外参数")
        inspect_application()
        return
    if arguments.command in {"start", "finish", "ask-contract", "review-pack"}:
        remaining = [arguments.command, *remaining]
    sys.argv = ["dev " + arguments.command, *remaining]
    runpy.run_module(COMMANDS[arguments.command], run_name="__main__")
