# 用户权限：操作与流程

> 本文件由 `uv run python -m tools.export_docs` 根据代码中的声明生成，不要手工修改；业务含义写在 needs.md 和 rules.md。

模块 `user_access`，版本 1。调用的其他模块：无。

## 公开操作

| 操作 | 名称 | 权限 | 接口 | 可能的业务错误 |
| --- | --- | --- | --- | --- |
| create_org | 创建组织 | user_access.system | POST /api/v1/access/orgs | user_access_conflict（组织代码、角色名或用户名已存在）、org_code_invalid（组织代码只能由小写字母、数字和短横线组成，长 3 至 32 字符；名称不能为空） |
| list_orgs | 查询组织 | user_access.manage | GET /api/v1/access/orgs | 无 |
| create_role | 创建角色 | user_access.manage | POST /api/v1/access/roles | user_access_conflict（组织代码、角色名或用户名已存在）、user_access_missing（组织、角色或用户不存在） |
| list_roles | 查询角色 | user_access.manage | GET /api/v1/access/roles | 无 |
| create_user | 创建用户 | user_access.manage | POST /api/v1/access/users | user_access_conflict（组织代码、角色名或用户名已存在）、user_access_missing（组织、角色或用户不存在） |
| list_users | 查询用户 | user_access.manage | GET /api/v1/access/users | 无 |
| change_user | 调整用户 | user_access.manage | PUT /api/v1/access/users | user_access_missing（组织、角色或用户不存在） |
| login | 用户登录 | public | POST /api/v1/access/login | login_failed（账号或密码不正确）、otp_required（需要两步验证码） |
| refresh | 刷新登录 | public | POST /api/v1/access/refresh | refresh_rejected（登录已失效，请重新登录） |
| logout | 退出登录 | public | POST /api/v1/access/logout | 无 |
| change_password | 修改密码 | signed_in | POST /api/v1/access/password | password_mismatch（原密码不正确） |
| purge_sessions | 清理过期刷新令牌 | user_access.system | 定时计划 | 无 |
| issue_reset | 生成密码重置码 | user_access.manage | POST /api/v1/access/users/reset-code | 无 |
| reset_password | 用重置码设置新密码 | public | POST /api/v1/access/password/reset | reset_invalid（重置码无效或已过期） |
| start_otp | 生成两步验证密钥 | signed_in | POST /api/v1/access/otp | otp_invalid（验证码不正确或已用过） |
| enable_otp | 开启两步验证 | signed_in | POST /api/v1/access/otp/enable | otp_invalid（验证码不正确或已用过） |
| disable_otp | 关闭两步验证 | signed_in | POST /api/v1/access/otp/disable | otp_invalid（验证码不正确或已用过） |
| reset_otp | 管理员关闭两步验证 | user_access.manage | POST /api/v1/access/users/otp/reset | 无 |

## 创建组织（user_access.create_org）

输入 `OrgInput`，输出 `OrgView`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：组织代码、组织名称"])
    s1["1. 创建组织（保存）<br/>规则 R-01"]:::save
    start --> s1
    finish(["结果：新建的组织"])
    s1 --> finish
    classDef compute fill:#eef6ff,stroke:#4a78b5
    classDef read fill:#f2fbf2,stroke:#4a9a4a
    classDef save fill:#fff4e5,stroke:#c07a1a
    classDef call fill:#f5f0ff,stroke:#7a5ab5
    classDef model fill:#ffeef4,stroke:#b54a7a
    classDef ok fill:#eaf7ea,stroke:#3c8c3c
    classDef failed fill:#fdeaea,stroke:#c03c3c,stroke-width:2px
    classDef skipped fill:#f2f2f2,stroke:#999,stroke-dasharray:4 3,color:#777
    classDef running fill:#fff8d6,stroke:#b59a1a
```

字段来源：

| 字段 | 含义 | 来源 | 写入步骤 | 规则 | 用到的字段 |
| --- | --- | --- | --- | --- | --- |
| code | 组织代码 | 操作输入 |  |  |  |
| name | 组织名称 | 操作输入 |  |  |  |
| result | 新建的组织 | 步骤 | 创建组织 | R-01 | code、name |

## 查询组织（user_access.list_orgs）

输入 `Nothing`，输出 `OrgList`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：无"])
    s1["1. 查询组织（数据访问）<br/>规则 R-04"]:::read
    start --> s1
    finish(["结果：可访问的组织"])
    s1 --> finish
    classDef compute fill:#eef6ff,stroke:#4a78b5
    classDef read fill:#f2fbf2,stroke:#4a9a4a
    classDef save fill:#fff4e5,stroke:#c07a1a
    classDef call fill:#f5f0ff,stroke:#7a5ab5
    classDef model fill:#ffeef4,stroke:#b54a7a
    classDef ok fill:#eaf7ea,stroke:#3c8c3c
    classDef failed fill:#fdeaea,stroke:#c03c3c,stroke-width:2px
    classDef skipped fill:#f2f2f2,stroke:#999,stroke-dasharray:4 3,color:#777
    classDef running fill:#fff8d6,stroke:#b59a1a
```

字段来源：

| 字段 | 含义 | 来源 | 写入步骤 | 规则 | 用到的字段 |
| --- | --- | --- | --- | --- | --- |
| result | 可访问的组织 | 步骤 | 查询组织 | R-04 |  |

## 创建角色（user_access.create_role）

输入 `RoleInput`，输出 `RoleView`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：角色所属组织代码、角色名称，在组织内唯一、角色拥有的权限名"])
    s1["1. 创建角色（保存）<br/>规则 R-02"]:::save
    start --> s1
    finish(["结果：新建的角色"])
    s1 --> finish
    classDef compute fill:#eef6ff,stroke:#4a78b5
    classDef read fill:#f2fbf2,stroke:#4a9a4a
    classDef save fill:#fff4e5,stroke:#c07a1a
    classDef call fill:#f5f0ff,stroke:#7a5ab5
    classDef model fill:#ffeef4,stroke:#b54a7a
    classDef ok fill:#eaf7ea,stroke:#3c8c3c
    classDef failed fill:#fdeaea,stroke:#c03c3c,stroke-width:2px
    classDef skipped fill:#f2f2f2,stroke:#999,stroke-dasharray:4 3,color:#777
    classDef running fill:#fff8d6,stroke:#b59a1a
```

字段来源：

| 字段 | 含义 | 来源 | 写入步骤 | 规则 | 用到的字段 |
| --- | --- | --- | --- | --- | --- |
| org_id | 角色所属组织 | 操作输入 |  |  |  |
| name | 角色名称 | 操作输入 |  |  |  |
| permissions | 角色权限 | 操作输入 |  |  |  |
| result | 新建的角色 | 步骤 | 创建角色 | R-02 | org_id、name、permissions |

## 查询角色（user_access.list_roles）

输入 `OrgQuery`，输出 `RoleList`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：要查询的组织代码"])
    s1["1. 查询角色（数据访问）<br/>规则 R-04"]:::read
    start --> s1
    finish(["结果：角色列表"])
    s1 --> finish
    classDef compute fill:#eef6ff,stroke:#4a78b5
    classDef read fill:#f2fbf2,stroke:#4a9a4a
    classDef save fill:#fff4e5,stroke:#c07a1a
    classDef call fill:#f5f0ff,stroke:#7a5ab5
    classDef model fill:#ffeef4,stroke:#b54a7a
    classDef ok fill:#eaf7ea,stroke:#3c8c3c
    classDef failed fill:#fdeaea,stroke:#c03c3c,stroke-width:2px
    classDef skipped fill:#f2f2f2,stroke:#999,stroke-dasharray:4 3,color:#777
    classDef running fill:#fff8d6,stroke:#b59a1a
```

字段来源：

| 字段 | 含义 | 来源 | 写入步骤 | 规则 | 用到的字段 |
| --- | --- | --- | --- | --- | --- |
| org_id | 要查询的组织 | 操作输入 |  |  |  |
| result | 角色列表 | 步骤 | 查询角色 | R-04 | org_id |

## 创建用户（user_access.create_user）

输入 `UserInput`，输出 `UserView`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：用户所属组织代码、用户名，在组织内唯一、登录密码、角色编号"])
    s1["1. 创建用户（保存）<br/>规则 R-02"]:::save
    start --> s1
    finish(["结果：新建的用户"])
    s1 --> finish
    classDef compute fill:#eef6ff,stroke:#4a78b5
    classDef read fill:#f2fbf2,stroke:#4a9a4a
    classDef save fill:#fff4e5,stroke:#c07a1a
    classDef call fill:#f5f0ff,stroke:#7a5ab5
    classDef model fill:#ffeef4,stroke:#b54a7a
    classDef ok fill:#eaf7ea,stroke:#3c8c3c
    classDef failed fill:#fdeaea,stroke:#c03c3c,stroke-width:2px
    classDef skipped fill:#f2f2f2,stroke:#999,stroke-dasharray:4 3,color:#777
    classDef running fill:#fff8d6,stroke:#b59a1a
```

字段来源：

| 字段 | 含义 | 来源 | 写入步骤 | 规则 | 用到的字段 |
| --- | --- | --- | --- | --- | --- |
| org_id | 用户所属组织 | 操作输入 |  |  |  |
| username | 用户名 | 操作输入 |  |  |  |
| password | 密码 | 操作输入 |  |  |  |
| role_id | 角色编号 | 操作输入 |  |  |  |
| result | 新建的用户 | 步骤 | 创建用户 | R-02 | org_id、username、password、role_id |

## 查询用户（user_access.list_users）

输入 `UserQuery`，输出 `CursorPage[UserView]`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：要查询的组织代码、上一页返回的 next_after、本页最多返回多少条"])
    s1["1. 查询用户（数据访问）<br/>规则 R-04"]:::read
    start --> s1
    finish(["结果：一页用户，按编号从小到大，不包含密码摘要"])
    s1 --> finish
    classDef compute fill:#eef6ff,stroke:#4a78b5
    classDef read fill:#f2fbf2,stroke:#4a9a4a
    classDef save fill:#fff4e5,stroke:#c07a1a
    classDef call fill:#f5f0ff,stroke:#7a5ab5
    classDef model fill:#ffeef4,stroke:#b54a7a
    classDef ok fill:#eaf7ea,stroke:#3c8c3c
    classDef failed fill:#fdeaea,stroke:#c03c3c,stroke-width:2px
    classDef skipped fill:#f2f2f2,stroke:#999,stroke-dasharray:4 3,color:#777
    classDef running fill:#fff8d6,stroke:#b59a1a
```

字段来源：

| 字段 | 含义 | 来源 | 写入步骤 | 规则 | 用到的字段 |
| --- | --- | --- | --- | --- | --- |
| org_id | 要查询的组织 | 操作输入 |  |  |  |
| after | 从哪个位置之后开始 | 操作输入 |  |  |  |
| limit | 本页最多返回多少条 | 操作输入 |  |  |  |
| result | 一页用户，按编号从小到大，不包含密码摘要 | 步骤 | 查询用户 | R-04 | org_id、after、limit |

## 调整用户（user_access.change_user）

输入 `UserChange`，输出 `UserView`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：用户所属组织代码、要修改的用户编号、修改后的角色编号、修改后是否允许登录"])
    s1["1. 调整用户（保存）<br/>规则 R-02"]:::save
    start --> s1
    finish(["结果：修改后的用户"])
    s1 --> finish
    classDef compute fill:#eef6ff,stroke:#4a78b5
    classDef read fill:#f2fbf2,stroke:#4a9a4a
    classDef save fill:#fff4e5,stroke:#c07a1a
    classDef call fill:#f5f0ff,stroke:#7a5ab5
    classDef model fill:#ffeef4,stroke:#b54a7a
    classDef ok fill:#eaf7ea,stroke:#3c8c3c
    classDef failed fill:#fdeaea,stroke:#c03c3c,stroke-width:2px
    classDef skipped fill:#f2f2f2,stroke:#999,stroke-dasharray:4 3,color:#777
    classDef running fill:#fff8d6,stroke:#b59a1a
```

字段来源：

| 字段 | 含义 | 来源 | 写入步骤 | 规则 | 用到的字段 |
| --- | --- | --- | --- | --- | --- |
| org_id | 用户所属组织 | 操作输入 |  |  |  |
| user_id | 要修改的用户编号 | 操作输入 |  |  |  |
| role_id | 修改后的角色 | 操作输入 |  |  |  |
| active | 修改后的启用状态 | 操作输入 |  |  |  |
| result | 修改后的用户 | 步骤 | 调整用户 | R-02 | org_id、user_id、role_id、active |

## 用户登录（user_access.login）

输入 `LoginInput`，输出 `SessionGrant`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：组织代码、用户名、密码、两步验证码"])
    s1["1. 校验登录（数据访问）<br/>规则 R-03"]:::read
    start --> s1
    s2["2. 建立登录会话（保存）<br/>规则 R-05"]:::save
    s1 --> s2
    finish(["结果：新建的登录会话"])
    s2 --> finish
    classDef compute fill:#eef6ff,stroke:#4a78b5
    classDef read fill:#f2fbf2,stroke:#4a9a4a
    classDef save fill:#fff4e5,stroke:#c07a1a
    classDef call fill:#f5f0ff,stroke:#7a5ab5
    classDef model fill:#ffeef4,stroke:#b54a7a
    classDef ok fill:#eaf7ea,stroke:#3c8c3c
    classDef failed fill:#fdeaea,stroke:#c03c3c,stroke-width:2px
    classDef skipped fill:#f2f2f2,stroke:#999,stroke-dasharray:4 3,color:#777
    classDef running fill:#fff8d6,stroke:#b59a1a
```

字段来源：

| 字段 | 含义 | 来源 | 写入步骤 | 规则 | 用到的字段 |
| --- | --- | --- | --- | --- | --- |
| org_code | 组织代码 | 操作输入 |  |  |  |
| username | 用户名 | 操作输入 |  |  |  |
| password | 密码 | 操作输入 |  |  |  |
| otp_code | 两步验证码 | 操作输入 |  |  |  |
| account | 经过密码校验的用户 | 步骤 | 校验登录 | R-03 | org_code、username、password、otp_code |
| result | 新建的登录会话 | 步骤 | 建立登录会话 | R-05 | account |

## 刷新登录（user_access.refresh）

输入 `RefreshInput`，输出 `SessionRenewal`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：刷新令牌"])
    s1["1. 检查刷新令牌（数据访问）<br/>规则 R-05"]:::read
    start --> s1
    s2["2. 轮换刷新令牌（保存）<br/>规则 R-05"]:::save
    s1 --> s2
    finish(["结果：换得的新会话"])
    s2 --> finish
    classDef compute fill:#eef6ff,stroke:#4a78b5
    classDef read fill:#f2fbf2,stroke:#4a9a4a
    classDef save fill:#fff4e5,stroke:#c07a1a
    classDef call fill:#f5f0ff,stroke:#7a5ab5
    classDef model fill:#ffeef4,stroke:#b54a7a
    classDef ok fill:#eaf7ea,stroke:#3c8c3c
    classDef failed fill:#fdeaea,stroke:#c03c3c,stroke-width:2px
    classDef skipped fill:#f2f2f2,stroke:#999,stroke-dasharray:4 3,color:#777
    classDef running fill:#fff8d6,stroke:#b59a1a
```

字段来源：

| 字段 | 含义 | 来源 | 写入步骤 | 规则 | 用到的字段 |
| --- | --- | --- | --- | --- | --- |
| refresh_token | 刷新令牌 | 操作输入 |  |  |  |
| check | 刷新令牌的检查结果 | 步骤 | 检查刷新令牌 | R-05 | refresh_token |
| result | 换得的新会话 | 步骤 | 轮换刷新令牌 | R-05 | check |

## 退出登录（user_access.logout）

输入 `RefreshInput`，输出 `Nothing`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：刷新令牌"])
    s1["1. 作废登录会话（保存）<br/>规则 R-05"]:::save
    start --> s1
    finish(["结果：没有返回内容"])
    s1 --> finish
    classDef compute fill:#eef6ff,stroke:#4a78b5
    classDef read fill:#f2fbf2,stroke:#4a9a4a
    classDef save fill:#fff4e5,stroke:#c07a1a
    classDef call fill:#f5f0ff,stroke:#7a5ab5
    classDef model fill:#ffeef4,stroke:#b54a7a
    classDef ok fill:#eaf7ea,stroke:#3c8c3c
    classDef failed fill:#fdeaea,stroke:#c03c3c,stroke-width:2px
    classDef skipped fill:#f2f2f2,stroke:#999,stroke-dasharray:4 3,color:#777
    classDef running fill:#fff8d6,stroke:#b59a1a
```

字段来源：

| 字段 | 含义 | 来源 | 写入步骤 | 规则 | 用到的字段 |
| --- | --- | --- | --- | --- | --- |
| refresh_token | 刷新令牌 | 操作输入 |  |  |  |
| result | 没有返回内容 | 步骤 | 作废登录会话 | R-05 | refresh_token |

## 修改密码（user_access.change_password）

输入 `PasswordChange`，输出 `Nothing`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：原密码、新密码"])
    s1["1. 检查原密码（数据访问）<br/>规则 R-06"]:::read
    start --> s1
    s2["2. 更新密码并作废会话（保存）<br/>规则 R-06"]:::save
    s1 --> s2
    finish(["结果：没有返回内容"])
    s2 --> finish
    classDef compute fill:#eef6ff,stroke:#4a78b5
    classDef read fill:#f2fbf2,stroke:#4a9a4a
    classDef save fill:#fff4e5,stroke:#c07a1a
    classDef call fill:#f5f0ff,stroke:#7a5ab5
    classDef model fill:#ffeef4,stroke:#b54a7a
    classDef ok fill:#eaf7ea,stroke:#3c8c3c
    classDef failed fill:#fdeaea,stroke:#c03c3c,stroke-width:2px
    classDef skipped fill:#f2f2f2,stroke:#999,stroke-dasharray:4 3,color:#777
    classDef running fill:#fff8d6,stroke:#b59a1a
```

字段来源：

| 字段 | 含义 | 来源 | 写入步骤 | 规则 | 用到的字段 |
| --- | --- | --- | --- | --- | --- |
| old_password | 原密码 | 操作输入 |  |  |  |
| new_password | 新密码 | 操作输入 |  |  |  |
| user_id | 检查过原密码的用户编号 | 步骤 | 检查原密码 | R-06 | old_password |
| result | 没有返回内容 | 步骤 | 更新密码并作废会话 | R-06 | user_id、new_password |

## 清理过期刷新令牌（user_access.purge_sessions）

输入 `Nothing`，输出 `PurgeResult`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：无"])
    s1["1. 清理过期刷新令牌（保存）<br/>规则 R-07"]:::save
    start --> s1
    finish(["结果：清理结果"])
    s1 --> finish
    classDef compute fill:#eef6ff,stroke:#4a78b5
    classDef read fill:#f2fbf2,stroke:#4a9a4a
    classDef save fill:#fff4e5,stroke:#c07a1a
    classDef call fill:#f5f0ff,stroke:#7a5ab5
    classDef model fill:#ffeef4,stroke:#b54a7a
    classDef ok fill:#eaf7ea,stroke:#3c8c3c
    classDef failed fill:#fdeaea,stroke:#c03c3c,stroke-width:2px
    classDef skipped fill:#f2f2f2,stroke:#999,stroke-dasharray:4 3,color:#777
    classDef running fill:#fff8d6,stroke:#b59a1a
```

字段来源：

| 字段 | 含义 | 来源 | 写入步骤 | 规则 | 用到的字段 |
| --- | --- | --- | --- | --- | --- |
| result | 清理结果 | 步骤 | 清理过期刷新令牌 | R-07 |  |

## 生成密码重置码（user_access.issue_reset）

输入 `UserRef`，输出 `ResetCode`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：用户所属组织代码、用户编号"])
    s1["1. 生成重置码（保存）<br/>规则 R-08"]:::save
    start --> s1
    finish(["结果：新的重置码"])
    s1 --> finish
    classDef compute fill:#eef6ff,stroke:#4a78b5
    classDef read fill:#f2fbf2,stroke:#4a9a4a
    classDef save fill:#fff4e5,stroke:#c07a1a
    classDef call fill:#f5f0ff,stroke:#7a5ab5
    classDef model fill:#ffeef4,stroke:#b54a7a
    classDef ok fill:#eaf7ea,stroke:#3c8c3c
    classDef failed fill:#fdeaea,stroke:#c03c3c,stroke-width:2px
    classDef skipped fill:#f2f2f2,stroke:#999,stroke-dasharray:4 3,color:#777
    classDef running fill:#fff8d6,stroke:#b59a1a
```

字段来源：

| 字段 | 含义 | 来源 | 写入步骤 | 规则 | 用到的字段 |
| --- | --- | --- | --- | --- | --- |
| org_id | 用户所属组织 | 操作输入 |  |  |  |
| user_id | 用户编号 | 操作输入 |  |  |  |
| result | 新的重置码 | 步骤 | 生成重置码 | R-08 | org_id、user_id |

## 用重置码设置新密码（user_access.reset_password）

输入 `ResetInput`，输出 `Nothing`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：组织代码、用户名、管理员给的重置码、新密码"])
    s1["1. 检查重置码（数据访问）<br/>规则 R-08"]:::read
    start --> s1
    s2["2. 用重置码设置新密码（保存）<br/>规则 R-08"]:::save
    s1 --> s2
    finish(["结果：没有返回内容"])
    s2 --> finish
    classDef compute fill:#eef6ff,stroke:#4a78b5
    classDef read fill:#f2fbf2,stroke:#4a9a4a
    classDef save fill:#fff4e5,stroke:#c07a1a
    classDef call fill:#f5f0ff,stroke:#7a5ab5
    classDef model fill:#ffeef4,stroke:#b54a7a
    classDef ok fill:#eaf7ea,stroke:#3c8c3c
    classDef failed fill:#fdeaea,stroke:#c03c3c,stroke-width:2px
    classDef skipped fill:#f2f2f2,stroke:#999,stroke-dasharray:4 3,color:#777
    classDef running fill:#fff8d6,stroke:#b59a1a
```

字段来源：

| 字段 | 含义 | 来源 | 写入步骤 | 规则 | 用到的字段 |
| --- | --- | --- | --- | --- | --- |
| org_code | 组织代码 | 操作输入 |  |  |  |
| username | 用户名 | 操作输入 |  |  |  |
| code | 重置码 | 操作输入 |  |  |  |
| new_password | 新密码 | 操作输入 |  |  |  |
| user_id | 重置码对应的用户编号 | 步骤 | 检查重置码 | R-08 | org_code、username、code |
| result | 没有返回内容 | 步骤 | 用重置码设置新密码 | R-08 | code、user_id、new_password |

## 生成两步验证密钥（user_access.start_otp）

输入 `Nothing`，输出 `OtpSetup`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：无"])
    s1["1. 生成两步验证密钥（保存）<br/>规则 R-09"]:::save
    start --> s1
    finish(["结果：待确认的两步验证密钥"])
    s1 --> finish
    classDef compute fill:#eef6ff,stroke:#4a78b5
    classDef read fill:#f2fbf2,stroke:#4a9a4a
    classDef save fill:#fff4e5,stroke:#c07a1a
    classDef call fill:#f5f0ff,stroke:#7a5ab5
    classDef model fill:#ffeef4,stroke:#b54a7a
    classDef ok fill:#eaf7ea,stroke:#3c8c3c
    classDef failed fill:#fdeaea,stroke:#c03c3c,stroke-width:2px
    classDef skipped fill:#f2f2f2,stroke:#999,stroke-dasharray:4 3,color:#777
    classDef running fill:#fff8d6,stroke:#b59a1a
```

字段来源：

| 字段 | 含义 | 来源 | 写入步骤 | 规则 | 用到的字段 |
| --- | --- | --- | --- | --- | --- |
| result | 待确认的两步验证密钥 | 步骤 | 生成两步验证密钥 | R-09 |  |

## 开启两步验证（user_access.enable_otp）

输入 `OtpCode`，输出 `Nothing`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：身份验证器应用显示的 6 位验证码"])
    s1["1. 确认并开启两步验证（保存）<br/>规则 R-09"]:::save
    start --> s1
    finish(["结果：没有返回内容"])
    s1 --> finish
    classDef compute fill:#eef6ff,stroke:#4a78b5
    classDef read fill:#f2fbf2,stroke:#4a9a4a
    classDef save fill:#fff4e5,stroke:#c07a1a
    classDef call fill:#f5f0ff,stroke:#7a5ab5
    classDef model fill:#ffeef4,stroke:#b54a7a
    classDef ok fill:#eaf7ea,stroke:#3c8c3c
    classDef failed fill:#fdeaea,stroke:#c03c3c,stroke-width:2px
    classDef skipped fill:#f2f2f2,stroke:#999,stroke-dasharray:4 3,color:#777
    classDef running fill:#fff8d6,stroke:#b59a1a
```

字段来源：

| 字段 | 含义 | 来源 | 写入步骤 | 规则 | 用到的字段 |
| --- | --- | --- | --- | --- | --- |
| code | 验证码 | 操作输入 |  |  |  |
| result | 没有返回内容 | 步骤 | 确认并开启两步验证 | R-09 | code |

## 关闭两步验证（user_access.disable_otp）

输入 `OtpCode`，输出 `Nothing`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：身份验证器应用显示的 6 位验证码"])
    s1["1. 确认并关闭两步验证（保存）<br/>规则 R-09"]:::save
    start --> s1
    finish(["结果：没有返回内容"])
    s1 --> finish
    classDef compute fill:#eef6ff,stroke:#4a78b5
    classDef read fill:#f2fbf2,stroke:#4a9a4a
    classDef save fill:#fff4e5,stroke:#c07a1a
    classDef call fill:#f5f0ff,stroke:#7a5ab5
    classDef model fill:#ffeef4,stroke:#b54a7a
    classDef ok fill:#eaf7ea,stroke:#3c8c3c
    classDef failed fill:#fdeaea,stroke:#c03c3c,stroke-width:2px
    classDef skipped fill:#f2f2f2,stroke:#999,stroke-dasharray:4 3,color:#777
    classDef running fill:#fff8d6,stroke:#b59a1a
```

字段来源：

| 字段 | 含义 | 来源 | 写入步骤 | 规则 | 用到的字段 |
| --- | --- | --- | --- | --- | --- |
| code | 验证码 | 操作输入 |  |  |  |
| result | 没有返回内容 | 步骤 | 确认并关闭两步验证 | R-09 | code |

## 管理员关闭两步验证（user_access.reset_otp）

输入 `UserRef`，输出 `Nothing`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：用户所属组织代码、用户编号"])
    s1["1. 管理员关闭两步验证（保存）<br/>规则 R-09"]:::save
    start --> s1
    finish(["结果：没有返回内容"])
    s1 --> finish
    classDef compute fill:#eef6ff,stroke:#4a78b5
    classDef read fill:#f2fbf2,stroke:#4a9a4a
    classDef save fill:#fff4e5,stroke:#c07a1a
    classDef call fill:#f5f0ff,stroke:#7a5ab5
    classDef model fill:#ffeef4,stroke:#b54a7a
    classDef ok fill:#eaf7ea,stroke:#3c8c3c
    classDef failed fill:#fdeaea,stroke:#c03c3c,stroke-width:2px
    classDef skipped fill:#f2f2f2,stroke:#999,stroke-dasharray:4 3,color:#777
    classDef running fill:#fff8d6,stroke:#b59a1a
```

字段来源：

| 字段 | 含义 | 来源 | 写入步骤 | 规则 | 用到的字段 |
| --- | --- | --- | --- | --- | --- |
| org_id | 用户所属组织 | 操作输入 |  |  |  |
| user_id | 用户编号 | 操作输入 |  |  |  |
| result | 没有返回内容 | 步骤 | 管理员关闭两步验证 | R-09 | org_id、user_id |

## 数据模型

### OrgInput

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| code | str | 是 | 组织代码 |  |  | R-01 |
| name | str | 是 | 组织名称 |  |  | R-01 |

### OrgView

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| code | str | 是 | 组织代码 |  |  | R-01 |
| name | str | 是 | 组织名称 |  |  | R-01 |

### Nothing

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |

### OrgList

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| items | list[OrgView] | 是 | 可访问的组织 |  |  |  |

### RoleInput

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| org_id | str | 是 | 角色所属组织代码 |  |  | R-02 |
| name | str | 是 | 角色名称，在组织内唯一 |  |  | R-02 |
| permissions | list[str] | 是 | 角色拥有的权限名 |  |  | R-02 |

### RoleView

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | int | 是 | 角色编号 |  |  |  |
| org_id | str | 是 | 角色所属组织代码 |  |  |  |
| name | str | 是 | 角色名称 |  |  |  |
| permissions | list[str] | 是 | 角色权限 |  |  |  |

### OrgQuery

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| org_id | str | 是 | 要查询的组织代码 |  |  | R-04 |

### RoleList

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| items | list[RoleView] | 是 | 可访问的角色 |  |  |  |

### UserInput

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| org_id | str | 是 | 用户所属组织代码 |  |  | R-02 |
| username | str | 是 | 用户名，在组织内唯一 |  |  | R-02 |
| password | str | 是 | 登录密码 |  |  | R-02 |
| role_id | int | 是 | 角色编号 |  |  | R-02 |

### UserView

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | int | 是 | 用户编号 |  |  |  |
| org_id | str | 是 | 用户所属组织代码 |  |  |  |
| username | str | 是 | 用户名 |  |  |  |
| role_id | int | 是 | 角色编号 |  |  |  |
| active | bool | 是 | 是否允许登录 |  |  |  |

### UserQuery

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| org_id | str | 是 | 要查询的组织代码 |  |  | R-04 |
| after | str | 否 | 上一页返回的 next_after |  | 从第一页开始 |  |
| limit | int | 否 | 本页最多返回多少条 |  |  |  |

### CursorPage[UserView]

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| items | list[UserView] | 是 | 本页记录 |  |  |  |
| next_after | str | 否 | 取下一页时作为 after 传回的位置 |  | 已经是最后一页 |  |

### UserChange

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| org_id | str | 是 | 用户所属组织代码 |  |  | R-02 |
| user_id | int | 是 | 要修改的用户编号 |  |  |  |
| role_id | int | 是 | 修改后的角色编号 |  |  | R-02 |
| active | bool | 是 | 修改后是否允许登录 |  |  | R-02 |

### LoginInput

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| org_code | str | 是 | 组织代码 |  |  | R-03 |
| username | str | 是 | 用户名 |  |  | R-03 |
| password | str | 是 | 密码 |  |  | R-03 |
| otp_code | str | 否 | 两步验证码 |  | 没有开启两步验证 | R-09 |

### SessionGrant

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| account | Account | 是 | 登录的用户及其当前权限 |  |  | R-05 |
| refresh_token | str | 是 | 新的刷新令牌原文，只在这次返回 |  |  | R-05 |
| refresh_expires_at | float | 是 | 刷新令牌失效时间 | Unix 秒 |  | R-05 |

### Account

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| user_id | int | 是 | 用户编号 |  |  | R-03 |
| org_id | str | 是 | 用户所属组织 |  |  | R-03 |
| username | str | 是 | 用户名 |  |  | R-03 |
| permissions | list[str] | 是 | 角色当前的权限，写进访问令牌 |  |  | R-03 |
| otp_step | int | 否 | 这次登录用掉的验证码周期 |  | 没有开启两步验证 | R-09 |

### RefreshInput

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| refresh_token | str | 是 | 刷新令牌 |  |  | R-05 |

### SessionRenewal

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| grant | SessionGrant \| None | 是 | 换得的新会话 |  | 刷新令牌无效、过期、已作废或被重复使用 | R-05 |

### PasswordChange

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| old_password | str | 是 | 原密码 |  |  | R-06 |
| new_password | str | 是 | 新密码 |  |  | R-06 |

### PurgeResult

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| removed | int | 是 | 删除的刷新令牌记录数 |  |  | R-07 |

### UserRef

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| org_id | str | 是 | 用户所属组织代码 |  |  | R-04 |
| user_id | int | 是 | 用户编号 |  |  |  |

### ResetCode

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| code | str | 是 | 一次性重置码，只返回这一次 |  |  | R-08 |
| expires_in | int | 是 | 还有多少秒失效 | 秒 |  | R-08 |

### ResetInput

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| org_code | str | 是 | 组织代码 |  |  | R-08 |
| username | str | 是 | 用户名 |  |  | R-08 |
| code | str | 是 | 管理员给的重置码 |  |  | R-08 |
| new_password | str | 是 | 新密码 |  |  | R-08 |

### OtpSetup

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| secret | str | 是 | 两步验证密钥，填进身份验证器应用 |  |  | R-09 |
| uri | str | 是 | 可生成二维码的地址 |  |  | R-09 |

### OtpCode

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| code | str | 是 | 身份验证器应用显示的 6 位验证码 |  |  | R-09 |

## 数据表

### user_access_orgs

| 列 | 类型 | 可空 | 主键 | 索引 |
| --- | --- | --- | --- | --- |
| code | VARCHAR(32) |  | 是 |  |
| name | VARCHAR(80) |  |  |  |

### user_access_roles

| 列 | 类型 | 可空 | 主键 | 索引 |
| --- | --- | --- | --- | --- |
| id | INTEGER |  | 是 |  |
| org_id | VARCHAR(32) |  |  |  |
| name | VARCHAR(64) |  |  |  |
| permissions | TEXT |  |  |  |

### user_access_users

| 列 | 类型 | 可空 | 主键 | 索引 |
| --- | --- | --- | --- | --- |
| id | INTEGER |  | 是 |  |
| org_id | VARCHAR(32) |  |  |  |
| username | VARCHAR(64) |  |  |  |
| password_hash | VARCHAR(192) |  |  |  |
| role_id | INTEGER |  |  |  |
| active | BOOLEAN |  |  |  |
| otp_secret | TEXT | 是 |  |  |
| otp_enabled | BOOLEAN |  |  |  |
| otp_last_step | INTEGER | 是 |  |  |

### user_access_refresh_tokens

| 列 | 类型 | 可空 | 主键 | 索引 |
| --- | --- | --- | --- | --- |
| token_sha256 | VARCHAR(64) |  | 是 |  |
| family_id | VARCHAR(32) |  |  | 是 |
| org_id | VARCHAR(32) |  |  |  |
| user_id | INTEGER |  |  | 是 |
| started_at | FLOAT |  |  |  |
| expires_at | FLOAT |  |  | 是 |
| used_at | FLOAT | 是 |  |  |
| revoked_at | FLOAT | 是 |  |  |

### user_access_reset_codes

| 列 | 类型 | 可空 | 主键 | 索引 |
| --- | --- | --- | --- | --- |
| code_sha256 | VARCHAR(64) |  | 是 |  |
| org_id | VARCHAR(32) |  |  |  |
| user_id | INTEGER |  |  | 是 |
| created_by | VARCHAR(120) |  |  |  |
| expires_at | FLOAT |  |  |  |
| used_at | FLOAT | 是 |  |  |
