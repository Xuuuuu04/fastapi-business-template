# 浏览器自动化

目前没有前端，只验证 Swagger API 文档渲染。默认测试不安装或启动浏览器。

先启动本机实例，再按需执行：

```bash
uv run --with playwright python -m playwright install chromium
uv run --with playwright python tests/browser/run.py --port 8000
```

Swagger 默认依赖外部 CDN，断网可能导致页面资源加载失败。此检查与 HTTP 文档测试不同：后者已纳入每次运行，但只能证明返回 HTML，不能证明浏览器渲染。

新增前端后在本目录按业务分包，优先使用可重复的测试数据；不要把截图或登录态提交进仓库。
