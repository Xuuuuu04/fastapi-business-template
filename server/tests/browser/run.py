"""
用浏览器打开本机的接口文档页面，检查页面能渲染、接口都列出、授权按钮存在。
需要额外安装：uv pip install playwright && uv run playwright install chromium。
用法：uv run python -m tests.browser.run --port 8000
"""

import argparse
import json
from urllib.request import urlopen

from playwright.sync_api import sync_playwright


# 打开文档页面并核对接口数量。
def main() -> None:
    parser = argparse.ArgumentParser(description="本机接口文档浏览器检查")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    base = f"http://127.0.0.1:{args.port}"
    with urlopen(f"{base}/openapi.json", timeout=10) as reply:
        schema = json.load(reply)
    expected = sum(len(item) for item in schema["paths"].values())
    with sync_playwright() as driver:
        browser = driver.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(f"{base}/docs")
            page.locator(".swagger-ui .opblock").first.wait_for()
            shown = page.locator(".swagger-ui .opblock").count()
            assert shown == expected, f"页面列出 {shown} 个接口，文档中有 {expected} 个"
            assert page.get_by_role("button", name="Authorize").count() >= 1
            print(f"浏览器检查通过：{shown} 个接口，授权按钮存在")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
