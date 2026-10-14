# 与前端对接

配套的前端是 Vue3 模板（`Vue3 前端模板`，同样采用开发包和固定文件的做法）。两边的约定只有下面这些，改动前先看这里。

## 前端依赖后端的什么

| 项目 | 约定 |
|---|---|
| 接口清单 | `doc/api/openapi.json`（`dev docs` 生成）。前端的 `api.ts` 和响应类型要和它保持一致 |
| 登录凭据 | 请求头 `Authorization: Bearer 令牌`。前端只在页面内存里保存令牌，刷新后重新登录 |
| 请求编号 | 前端每个请求带 `X-Request-ID`；后端响应头回带同一个 `X-Request-ID`，有运行记录时还带 `X-Run-ID` |
| 错误响应 | JSON：`code`、`kind`、`message`、`request_id`、`run_id`、`fields`（字段问题列表）。前端显示 `message` 的前 300 个字，按 `code` 区分 |
| 写入结果未知 | 前端把 5xx、408、499、网络中断、成功响应无法解析都当作"结果未知"，不自动重发，先查询。所以写接口要能查到结果，重复提交要有幂等保护 |
| 删除成功 | 返回 204，前端只认 204 为完成 |
| 文件下载 | 返回二进制内容；上传是 multipart，文件字段名由接口约定 |
| 同源 | 前端开发时把 `/api` 代理到后端（默认 `http://127.0.0.1:8000`），生产由网关把前端和 `/api` 放在同一个域名下 |

## 登录约定

模板本身不登记业务包。需要账号登录时，在 `server/` 执行 `uv run dev new-module user_access --title 账号登录 --preset access`，生成的最小账号包和前端模板 `src/app/login.config.ts` 的默认值一致：

| 项目 | 约定 |
|---|---|
| 登录接口 | `POST /api/v1/access/login`，不需要凭据 |
| 请求字段 | `org_code`、`username`、`password` 必填；`otp_code` 可以是空字符串，最小账号包不使用它 |
| 成功回包 | `access_token`、`token_type`（固定 `Bearer`）、`expires_in`（秒，等于 `APP_TOKEN_MINUTES` 乘 60）、`org_id` |
| 失败回包 | 口令不对和账号不存在都是 401，`code` 为 `包名_login_failed`；失败次数超限是 429 |
| 令牌内容 | HS256，由 `shared/access/tokens.py` 的 `issue_token` 签发；声明里有 `sub`、`name`、`org`、`permissions` 和有效期 |
| 权限写法 | 与 `Caller` 相同：`public`、`signed_in`、`*`、`模块名.动作`、`模块名.*`。前端只读令牌里的 `permissions` 决定页面提示，不调用“当前用户”接口；是否允许访问仍由后端判断 |
| 新建账号 | `POST /api/v1/access/accounts`，需要 `包名.manage`；只能在自己的组织里建，授予的权限不能超出自己的权限 |

第一个管理账号用服务密钥建：`uv run dev make-key --name 账号管理 --org-id 组织代码 --permissions user_access.manage`，把输出的摘要放进 `APP_API_KEYS`，再带 `X-API-Key` 调用新建账号接口。不分组织的产品，在前端 `login.config.ts` 的 `body` 里补上固定的组织代码。角色、停用、改口令、刷新令牌和两步验证不在最小账号包里，产品需要时自己加，并同步改前端的登录约定。

## 改接口时

1. 改完代码后运行 `uv run dev docs`，看 `doc/api/openapi.json` 的差异。
2. 删除字段、改名、把必填改成可选、改枚举值，都会让前端运行时报"返回的数据格式不符合约定"。这类改动要先在前端的 `api.ts`、`data.ts` 里同步，或者保留旧字段一段时间。
3. 新增字段不影响前端（前端只检查它声明的字段），但前端要用的话得先登记。
4. 用 `uv run dev compare-api --before 改前 --after 改后` 比较改前改后的两份 openapi，把差异告诉做前端的人。

## 前端出错时怎么查

前端“开发者工具 → 操作记录”里，每次操作的请求记录都有 `X-Request-ID` 和（如果有的话）`X-Run-ID`。拿运行编号到 `/system/console`、`/api/system/runs/{run_id}/report` 或 `uv run dev diagnose run 运行编号` 查看后端的执行过程。没有 `X-Run-ID`，说明这次请求没有进入登记的操作（比如认证失败、路由不存在），先按请求编号查日志。

## 在真实后台上验证前端

只在用户明确提供的隔离测试环境、账号和数据上做。前端用 `VITE_API_MODE=real` 连到这个后端，先登录，再按页面逐项操作，并确认只读账号看不到写入口。前端的 `npm run test:browser` 用的是独立演示服务，不代表真实后台已经接通。运行前确认这个后端的组织和账号是专门用于测试的；运行后记录后端版本、账号权限、通过的操作。没有验证过的部分保持“未验证”。
