# 全局 API 文档

export.py 从实际应用的全部路由生成 out/api/openapi.json 和中文 out/api/index.md。运行 uv run python -m app.api.docs.export，不启动资源、不连接数据库。

文档包含接口用途、参数、正文、成功和错误响应、模型、示例和写入密钥说明。在线查看 /docs、/redoc 或 /openapi.json。

compare.py 比较接口新增、删除、声明变化以及共享模型和权限变化。使用 --before 和 --after 指定 JSON 文件。当前不自动判定兼容性，也未提供独立子应用汇总。
