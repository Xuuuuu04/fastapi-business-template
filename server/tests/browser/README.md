# browser：浏览器检查

打开本机的接口文档页面 `/docs`，检查页面能渲染、接口数量与 OpenAPI 描述一致、授权按钮存在。需要先启动服务，并额外安装 Playwright：

```bash
uv pip install playwright && uv run playwright install chromium
uv run python -m tests.browser.run --port 8000
```

以后有前端时，前端流程的浏览器测试也放在这里。
