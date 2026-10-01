# browser：浏览器检查

打开本机接口文档，检查接口数量和服务密钥、登录令牌两种认证方式，并保存截图。
设置 `APP_TEST_SERVICE_KEY` 后，也检查运行页面的五个查询入口、模块步骤和运行详情是否与接口一致。
服务需要开启 `APP_DOCS=true`；检查运行页面时还需开启 `APP_CONSOLE=true`。

```bash
uv run --with playwright python -m playwright install chromium
uv run --with playwright python -m tests.browser.run --port 8000 --output out/browser
```

服务密钥通过环境变量提供，不写入命令行参数。截图仍需人工检查布局和可读性。
