"""
生成离线单文件开发面板，只读当前产品声明和本机证据，不启动业务服务。
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

from fastapi_check.quality.rules import PROJECT
from fastapi_project.development.check_assets import atomic_bytes
from fastapi_project.development.panel_data import panel_data

from app.setup.application import application_modules
from shared.modules.catalog import Catalog

ASSETS = Path(__file__).resolve().parents[2] / "assets/panel"


# JSON中转义脚本终止符和特殊分隔符，业务标题不能注入HTML或脚本。
def embedded_json(data: dict) -> str:
    return (
        json.dumps(data, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


# 图布局库与许可证随模板打包，运行生成命令时不联网下载。
def render(data: dict) -> str:
    library = (ASSETS / "dagre-1.1.8.min.js").read_text()
    vendor = json.loads((ASSETS / "vendor.json").read_text())
    if hashlib.sha256(library.encode()).hexdigest() != vendor["sha256"]:
        raise ValueError("离线布局库摘要不一致，请核对模板资产")
    document = (ASSETS / "page.html").read_text()
    parts = {
        "STYLE": (ASSETS / "style.css").read_text(),
        "DATA": embedded_json(data),
        "LAYOUT": library,
        "SCRIPT": (ASSETS / "panel.js").read_text(),
        "LICENSE": (ASSETS / "dagre-LICENSE.txt").read_text().replace("--", "- -"),
    }
    return re.sub(
        r"@@(STYLE|DATA|LAYOUT|SCRIPT|LICENSE)@@", lambda match: parts[match[1]], document
    )


# 只写派生HTML，不改任务卡、规则、分支、检查记录或业务数据库。
def generate(project: Path, catalog: Catalog) -> Path:
    path = project / "out/panel/index.html"
    try:
        data = panel_data(project, catalog)
    except (ValueError, OSError):
        atomic_bytes(
            path,
            (
                '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
                "<title>开发面板证据无法读取</title><body><h1>证据无法读取</h1>"
                "<p>请按命令错误核对本机原件。此前生成的面板已替换，不能继续作为当前通过的证据。</p>"
                "</body></html>"
            ).encode(),
        )
        raise
    atomic_bytes(path, render(data).encode())
    return path


# 命令输出文件位置，浏览器打开由使用者选择，不引入本地服务器。
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    path = generate(PROJECT, Catalog(application_modules()))
    print(json.dumps({"file": str(path), "offline": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
