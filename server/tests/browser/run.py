"""
用独立浏览器检查接口文档和运行页面，可保存截图供人工检查。
需要额外安装：uv run --with playwright python -m playwright install chromium。
用法：uv run --with playwright python -m tests.browser.run --port 8000 --output out/browser
设置 APP_TEST_SERVICE_KEY 后，同时检查运行页面的五个查询入口、模块步骤和运行详情。
"""

import argparse
import json
import os
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import Page, sync_playwright


# 文档中应列出实际接口，并同时提供两种认证方式。
def check_docs(page: Page, base: str, output: Path) -> int:
    with urlopen(f"{base}/openapi.json", timeout=10) as reply:
        schema = json.load(reply)
    expected = sum(len(item) for item in schema["paths"].values())
    page.goto(f"{base}/docs")
    page.locator(".swagger-ui .opblock").first.wait_for()
    shown = page.locator(".swagger-ui .opblock").count()
    assert shown == expected, f"页面列出 {shown} 个接口，文档中有 {expected} 个"
    page.screenshot(path=str(output / "docs.png"))
    page.get_by_role("button", name="Authorize", exact=True).click()
    dialog = page.locator(".dialog-ux")
    assert "服务密钥" in dialog.inner_text() and "登录令牌" in dialog.inner_text()
    page.screenshot(path=str(output / "authorization.png"))
    page.get_by_role("button", name="Close", exact=True).first.click()
    return shown


# 未填写凭据时提示；列表、模块步骤和运行详情与接口中的业务名称和结果一致。
def check_console(page: Page, base: str, key: str, output: Path) -> None:
    page.goto(f"{base}/system/console")
    page.get_by_role("button", name="最近运行", exact=True).click()
    assert page.get_by_role("status").inner_text() == "请先输入凭据。"
    page.get_by_label("凭据", exact=True).fill(key)
    for title, path in (
        ("模块关系", "modules"),
        ("最近运行", "runs"),
        ("运行统计", "stats"),
        ("进程状态", "runtime"),
        ("操作记录", "audit"),
    ):
        with page.expect_response(f"{base}/api/system/{path}") as pending:
            page.get_by_role("button", name=title, exact=True).click()
        response = pending.value
        assert response.status == 200, f"{title}请求失败：{response.status}"
        wait_results(page)
        data = response.json()
        assert (
            json.loads(page.locator("#results > details").last.locator("pre").text_content())
            == data
        )
        if "items" in data:
            assert page.locator("#results tbody tr").count() == len(data["items"])
        if path == "modules":
            check_module_flow(page, base, data, output)
        elif path == "runs" and data["items"]:
            assert data["items"][0]["title"] in page.locator("#results tbody").inner_text()
        page.screenshot(path=str(output / f"console-{path}.png"))
    runs = page.request.get(f"{base}/api/system/runs", headers={"X-API-Key": key}).json()
    if runs["items"]:
        check_run_detail(page, base, runs["items"][0]["id"], output)
    page.get_by_label("凭据", exact=True).fill("")


# 等待内容渲染完成，避免在请求刚返回时读取旧页面。
def wait_results(page: Page) -> None:
    page.wait_for_function("document.querySelector('#notice').textContent === '查询完成。'")


# 模块名称来自登记清单；打开第一个操作后，图中的步骤名称和顺序应与声明一致。
def check_module_flow(page: Page, base: str, data: dict, output: Path) -> None:
    assert page.locator(".cards article h3").all_text_contents() == [
        item["title"] for item in data["modules"]
    ]
    page.screenshot(path=str(output / "console-modules.png"))
    if not data["modules"]:
        return
    operation = data["modules"][0]["operations"][0]
    with page.expect_response(f"{base}/api/system/flows/{operation['name']}") as pending:
        page.locator(".cards article").first.get_by_role(
            "button", name=operation["title"], exact=True
        ).click()
    assert pending.value.status == 200
    wait_results(page)
    steps = pending.value.json()["steps"]
    shown = page.locator(".steps > li h3").all_text_contents()
    assert len(shown) == len(steps)
    assert all(part["title"] in text for part, text in zip(steps, shown, strict=True))
    page.screenshot(path=str(output / "console-flow.png"))
    page.get_by_role("button", name="模块关系", exact=True).click()
    wait_results(page)


# 运行详情逐步显示状态、耗时和失败原因，下层调用独立成组。
def check_run_detail(page: Page, base: str, run_id: str, output: Path) -> None:
    page.get_by_label("运行编号", exact=True).fill(run_id)
    with page.expect_response(f"{base}/api/system/runs/{run_id}") as pending:
        page.get_by_role("button", name="查看运行详情", exact=True).click()
    assert pending.value.status == 200
    wait_results(page)
    data = pending.value.json()
    for run in data["runs"]:
        card = page.locator(f"#run-{run['id']}")
        assert card.locator(":scope > h3").inner_text() == run["title"]
        assert card.locator(".steps > li").count() == len(run["steps"])
        if run["error_message"]:
            assert run["error_message"] in card.inner_text()
        for index, step in enumerate(run["steps"]):
            row = card.locator(".steps > li").nth(index)
            assert step["title"] in row.inner_text()
            assert f"{step['elapsed_ms']:.1f} 毫秒" in row.inner_text()
    page.screenshot(path=str(output / "console-report.png"))


# 按指定地址运行页面检查并保存截图。
def main() -> None:
    parser = argparse.ArgumentParser(description="本机页面检查")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--output", type=Path, default=Path("out/browser"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    base = f"http://127.0.0.1:{args.port}"
    with sync_playwright() as driver:
        browser = driver.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            shown = check_docs(page, base, args.output)
            key = os.environ.get("APP_TEST_SERVICE_KEY", "")
            if key:
                check_console(page, base, key, args.output)
            print(
                f"浏览器检查通过：{shown} 个接口、两种认证；运行页面{'已检查' if key else '未检查'}"
            )
        finally:
            browser.close()


if __name__ == "__main__":
    main()
