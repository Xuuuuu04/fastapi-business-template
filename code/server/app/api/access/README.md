# 写入访问检查

key.py 使用 FastAPI APIKeyHeader 检查 X-API-Key，与 OpenAPI 权限说明保持一致。读取笔记公开，创建、更新、删除需要 APP_WRITE_KEY。

未配置密钥返回 503，缺少或错误密钥返回 401。这是本地体验用的共享密钥方式，尚未实现账号、角色和对象权限。
