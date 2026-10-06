"""
从代码中的声明生成文档，不启动服务、不连接数据库。生成的文档都提交到仓库，改动时差异可见：
- doc/api/openapi.json 与 doc/api/index.md：接口描述和中文接口清单；
- doc/modules.md：模块关系图；
- doc/模块名/flows.md：操作、接口路径、流程图、字段来源、数据模型、数据表；
- doc/progress.md：进度与质量：待确认的业务问题、规则的测试标注、任务清单条数。
命令参数与调用方法见本功能所属项目 Skill。
"""

import argparse
import json
import sys
from pathlib import Path

from fastapi_check.quality.rules import PROJECT
from fastapi_docs.api_doc import api_markdown, docs_app
from fastapi_docs.flow_doc import HEADER, module_doc, route_map
from fastapi_docs.progress_doc import progress_doc
from fastapi_project.development.design import design_doc
from fastapi_project.development.plan import read_plan

from app.setup.catalog import MODULES
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
    app = docs_app(plan["name"] if plan else None)
    schema, markdown = api_markdown(app)
    routes = route_map(app)
    files = {
        project / "doc" / "modules.md": modules_doc(catalog),
        project / "doc" / "progress.md": progress_doc(catalog, project),
        project / "doc" / "development.md": design_doc(catalog, project),
        project / "doc" / "api" / "openapi.json": json.dumps(schema, ensure_ascii=False, indent=2)
        + "\n",
        project / "doc" / "api" / "index.md": markdown + "\n",
    }
    for name, module in catalog.modules.items():
        files[project / module.doc / "flows.md"] = module_doc(catalog, name, routes)
    return files


# 找出内容已过期的生成文档。
def outdated(catalog: Catalog, project: Path = PROJECT) -> list[Path]:
    return [
        path
        for path, text in generated(catalog, project).items()
        if not path.exists() or path.read_text(encoding="utf-8") != text
    ]


# 写入全部文档；check 为真时只比较。
def main() -> None:
    parser = argparse.ArgumentParser(description="从声明生成接口文档、模块流程文档和进度文档")
    parser.add_argument("--check", action="store_true", help="只检查文档是否过期，不写入")
    args = parser.parse_args()
    catalog = Catalog(MODULES)
    if args.check:
        stale = outdated(catalog)
        for path in stale:
            print(f"文档已过期：{path.relative_to(PROJECT)}")
        sys.exit(1 if stale else 0)
    files = generated(catalog)
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(f"已生成 {len(files)} 份文档：接口描述、模块关系、各模块流程、开发进度")


if __name__ == "__main__":
    main()
