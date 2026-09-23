"""
通过浏览器验证本机 API 文档页面。
需要额外安装 Playwright 和 Chromium，不在默认测试中运行。
"""

import argparse

from playwright.sync_api import sync_playwright


# 打开本机文档并检查接口渲染和授权按钮。
def main() -> None:
    parser = argparse.ArgumentParser(description="本机 API 文档浏览器检查")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("端口须为 1 至 65535")
    with sync_playwright() as driver:
        browser = driver.chromium.launch()
        try:
            page = browser.new_page()
            reply = page.goto(f"http://127.0.0.1:{args.port}/docs")
            assert reply is not None and reply.status == 200
            page.locator(".swagger-ui .opblock").first.wait_for()
            assert page.locator(".swagger-ui .opblock").count() == 10
            assert page.get_by_role("button", name="Authorize", exact=True).count() >= 1
            print("浏览器检查通过：文档页面、十个接口和授权入口")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
