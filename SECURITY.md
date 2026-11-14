# 安全策略

这份说明面向使用者与安全研究人员，介绍如何私下报告安全漏洞，以及模板内置的安全边界与下游产品需要自行承担的配置责任。

## 支持的版本

当前维护主分支最新的 `5.x` 版本。使用模板初始化的下游产品可以通过 `uv run dev upgrade` 合并框架层的安全修复。

## 如何报告漏洞

如果发现框架层存在认证绕过、跨组织数据越权、注入风险、密钥泄露或路径穿越等安全漏洞，请**不要直接提交公开 Issue**：

1. 请通过 GitHub 私密漏洞报告（仓库 Security 标签页下的 **Report a vulnerability**）提交详情。
2. 报告请写明受影响的版本或提交号、触发条件、最小复现步骤及实际影响范围。
3. 请不要在报告中附带任何真实生产系统的密钥或客户隐私数据。

维护者收到报告后会尽快确认可复现性，并在修复补丁与升级说明发布后公开致谢。

## 框架内置的安全机制

- **多层操作权限校验**：每个操作在 `contract` 中声明 `access` 权限，HTTP 入口、包内 `call` 调用、`later` 提交与后台 worker 执行时都会核对权限；调用者身份只来自已验签的凭据。
- **跨组织与负责人数据隔离**：带 `org_column()` 或 `owner_column()` 的数据表在 SQLAlchemy Core 执行前逐层检查查询条件，缺少 `org_id == caller.org_id` 或负责人条件时会直接拒绝执行。
- **凭据摘要与密钥轮换**：服务密钥由 `uv run dev make-key` 生成，配置中只保存 SHA-256 摘要；JWT 支持 `APP_JWT_PREVIOUS_SECRETS` 平滑轮换；敏感业务字段通过 `Vault`（`APP_DATA_KEYS`）加密保存。
- **脱敏运行记录与安全响应头**：标记 `secret=True` 的字段从不写入运行记录，普通字段默认只记类型、数量或长度；生产日志不含请求正文，意外异常只记录类型与源码行号；默认返回 `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY` 和 `Cache-Control: no-store`。
- **生产启动配置硬检查**：`APP_ENV=production` 时会自动拒绝默认弱密钥、`APP_DEV_CALLER=true`、内存运行记录、SQLite 数据库或缺失的外部系统凭据，且默认关闭 `/system/console` 排查网页。

## 下游产品仍需负责的事项

- 部署 HTTPS 反向代理，按实际代理地址收紧 `FORWARDED_ALLOW_IPS` 与 `APP_CORS`，确认全站 HTTPS 后再开启 `APP_HSTS_SECONDS`。
- 妥善保管生产环境的 `DATABASE_PASSWORD`、`APP_JWT_SECRET`、`APP_DATA_KEYS` 和 `APP_API_KEYS`，定期轮换密钥。
- 按业务规则设计具体角色权限与对象归属判断，对上传文件的内容安全（如病毒扫描或业务格式深检）按产品需求补充校验。
