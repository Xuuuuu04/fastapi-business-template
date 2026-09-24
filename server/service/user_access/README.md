# 用户权限（user_access）

## 职责

管理组织、组织内的角色与用户，校验密码登录，维护登录会话（刷新令牌的签发、轮换、作废）。访问令牌由接口层签发和校验；其他模块只接收已校验的调用者身份。

## 公开操作

| 操作 | 用途 | 权限 |
| --- | --- | --- |
| `user_access.create_org` | 创建组织 | `user_access.system` |
| `user_access.list_orgs` | 查询组织 | `user_access.manage` |
| `user_access.create_role` | 创建角色 | `user_access.manage` |
| `user_access.list_roles` | 查询角色 | `user_access.manage` |
| `user_access.create_user` | 创建用户 | `user_access.manage` |
| `user_access.list_users` | 查询用户 | `user_access.manage` |
| `user_access.change_user` | 调整用户状态和角色 | `user_access.manage` |
| `user_access.login` | 核对组织、账号、密码、启用状态和两步验证码，开始登录会话 | `public` |
| `user_access.refresh` | 用刷新令牌换新令牌；重复使用时作废整组会话 | `public` |
| `user_access.logout` | 作废这次登录会话 | `public` |
| `user_access.change_password` | 修改自己的密码并作废全部会话 | `signed_in` |
| `user_access.purge_sessions` | 每日清理过期和作废的刷新令牌记录 | `user_access.system` |
| `user_access.issue_reset` | 为本组织用户生成一次性密码重置码（R-08） | `user_access.manage` |
| `user_access.reset_password` | 用重置码设置新密码并作废全部会话（R-08） | `public` |
| `user_access.start_otp` | 生成两步验证密钥（R-09） | `signed_in` |
| `user_access.enable_otp` | 用当前验证码确认，开启两步验证 | `signed_in` |
| `user_access.disable_otp` | 用当前验证码确认，关闭两步验证 | `signed_in` |
| `user_access.reset_otp` | 管理员为本组织用户关闭两步验证 | `user_access.manage` |

## 依赖

使用框架提供的数据库、调用者身份和审计记录；没有其他业务模块依赖。

## 内部组织

- `data.py` 定义输入、输出及流程字段，`data_security.py` 是找回密码和两步验证的部分；`flow.py` 连接步骤。
- `steps/access.py` 是管理操作的步骤，`steps/sessions.py` 是登录会话的步骤，`steps/security.py` 是找回密码和两步验证的步骤。
- `store/sql.py` 核对组织和角色归属；`store/sessions.py` 管理刷新令牌，刷新令牌只保存摘要。
- `store/password.py` 使用带随机盐的 scrypt 摘要；`store/security.py` 管理重置码和两步验证，密钥用 `vault` 加密保存，用掉重置码和验证码周期都用带条件修改；`store/totp.py` 计算验证码；表定义位于 `store/tables.py`。
- 调整用户、修改密码、关闭两步验证都用 `update_tracked` 记入变更历史，密码摘要和两步验证密钥只记“已隐藏”。

## 业务文档

业务规则和确认样例见 [doc/user_access](../../../doc/user_access/rules.md)。项目启用前需核对组织划分与权限集合。

## 测试

`tests/integration/user_access/` 从 HTTP 入口检查管理、登录、跨组织拒绝、刷新令牌轮换与重复使用、停用、改密码、退出登录、清理、重置码找回密码和两步验证；`tests/modules/user_access/` 检查密码摘要和验证码计算（RFC 6238 测试向量）。
