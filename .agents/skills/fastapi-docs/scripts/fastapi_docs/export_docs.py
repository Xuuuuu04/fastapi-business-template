"""
从声明生成文档，不连接数据库；API/模块flows/AGENTS生成段提交。
模块关系/开发图/进度汇总及业务现状只在本机；现状生成与手写分开，过期检查不自动刷新。
命令参数与调用方法见本功能所属项目 Skill。
"""

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from fastapi_check.quality.rules import PROJECT
from fastapi_docs.api_doc import api_markdown, docs_app
from fastapi_docs.entry_state import render, stale
from fastapi_docs.flow_doc import HEADER, module_doc, route_map
from fastapi_docs.progress_doc import progress_doc
from fastapi_project.development.business_state import database_identity
from fastapi_project.development.business_state import outdated as state_outdated
from fastapi_project.development.business_state import update as update_state
from fastapi_project.development.design import design_doc
from fastapi_project.development.plan import read_plan
from fastapi_project.development.plan_entries import capture, check_entries

from app.setup.application import application, application_modules
from app.setup.operations import with_operations
from shared.config.settings import Settings
from shared.graphs.static import module_graph
from shared.modules.catalog import Catalog

API_DIR = PROJECT / "doc" / "api"


# 生成 doc/modules.md：全部模块和它们之间的调用关系。
def modules_doc(catalog: Catalog) -> str:
    lines = ["# 模块关系", "", HEADER.replace("needs.md 和 rules.md", "各模块目录"), ""]
    lines += ["| 模块 | 名称 | 版本 | 业务文档 |", "| --- | --- | --- | --- |"]
    for module in catalog.modules.values():
        link = f"[{module.name}/]({module.name}/)"
        lines.append(f"| {module.name} | {module.title} | {module.version} | {link} |")
    lines += ["", "```mermaid", module_graph(catalog), "```", ""]
    return "\n".join(lines)


# 列出全部应生成的文档及其内容。
def generated(catalog: Catalog, project: Path = PROJECT) -> dict[Path, str]:
    plan = read_plan(project)
    problems = check_entries(catalog, project, plan)
    if problems:
        raise ValueError("\n".join(problems))
    app = docs_app(plan["name"] if plan else None)
    schema, markdown = api_markdown(app)
    routes = route_map(app)
    files = {
        project / "doc" / "api" / "openapi.json": json.dumps(schema, ensure_ascii=False, indent=2)
        + "\n",
        project / "doc" / "api" / "index.md": markdown + "\n",
    }
    for name, module in catalog.modules.items():
        files[project / module.doc / "flows.md"] = module_doc(catalog, name, routes)
    return files


# 找出内容已过期的生成文档。
def outdated(catalog: Catalog, project: Path = PROJECT) -> list[Path]:
    result = [
        path
        for path, text in generated(catalog, project).items()
        if not path.exists() or path.read_text(encoding="utf-8") != text
    ]
    if stale(catalog, project, set(application().settings("offline").disabled_modules)):
        result.append(project / "AGENTS.md")
    settings = application().settings("offline")
    result += state_outdated(
        state_catalog(catalog, settings),
        project,
        set(settings.disabled_modules),
        database_id=database_identity(settings.database_url),
    )
    return result


# 已展开的流程入口先还原，避免重复生成JobPlan；内置运维只进入本机业务现状。
def state_catalog(catalog: Catalog, settings: Settings) -> Catalog:
    if not settings.operations.enabled():
        return catalog
    modules = []
    for module in catalog.modules.values():
        if module.name == "system_ops":
            continue
        starts = {pipeline.start for pipeline in module.pipelines}
        modules.append(
            replace(
                module,
                provides={op: flow for op, flow in module.provides.items() if op not in starts},
                jobs=tuple(plan for plan in module.jobs if plan.contract not in starts),
            )
        )
    return Catalog(with_operations(settings, modules))


# 汇总文档可重新生成，不参与源码提交或过期比较。
def summaries(catalog: Catalog, project: Path = PROJECT) -> dict[Path, str]:
    return {
        project / "doc" / "modules.md": modules_doc(catalog),
        project / "doc" / "progress.md": progress_doc(catalog, project),
        project / "doc" / "development.md": design_doc(catalog, project),
    }


# 写入全部文档；check 为真时只比较。
def main() -> None:
    parser = argparse.ArgumentParser(description="从声明生成接口文档、模块流程文档和进度文档")
    parser.add_argument("--check", action="store_true", help="只检查文档是否过期，不写入")
    args = parser.parse_args()
    catalog = Catalog(application_modules())
    if args.check:
        for path, text in summaries(catalog).items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        stale = outdated(catalog)
        for path in stale:
            print(f"文档已过期：{path.relative_to(PROJECT)}")
        sys.exit(1 if stale else 0)
    plan = read_plan(PROJECT)
    problems = check_entries(catalog, PROJECT, plan)
    if problems:
        raise SystemExit("\n".join(problems))
    capture(catalog, PROJECT, plan)
    files = generated(catalog) | summaries(catalog)
    files[PROJECT / "AGENTS.md"] = render(
        catalog, PROJECT, set(application().settings("offline").disabled_modules)
    )
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    settings = application().settings("offline")
    effective = state_catalog(catalog, settings)
    names = [
        path.stem
        for path in state_outdated(
            effective,
            PROJECT,
            set(settings.disabled_modules),
            database_id=database_identity(settings.database_url),
        )
    ]
    paths = update_state(effective, PROJECT, set(settings.disabled_modules), names=names)
    print(f"已生成 {len(files)} 份文档和 {len(paths)} 份本机业务现状；运行状态未读取时标未知")


if __name__ == "__main__":
    main()
