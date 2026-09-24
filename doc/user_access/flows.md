# 用户权限：操作与流程

> 本文件由 `uv run python -m tools.export_docs` 根据代码中的声明生成，不要手工修改；业务含义写在 needs.md 和 rules.md。

模块 `user_access`，版本 1。调用的其他模块：无。

## 公开操作

| 操作 | 名称 | 权限 | 调用方式 | 可能的业务错误 |
| --- | --- | --- | --- | --- |
| create_org | 创建组织 | user_access.system | 接口或任务 | user_access_conflict（组织代码、角色名或用户名已存在） |
| list_orgs | 查询组织 | user_access.manage | 接口或任务 | 无 |
| create_role | 创建角色 | user_access.manage | 接口或任务 | user_access_conflict（组织代码、角色名或用户名已存在）、user_access_missing（组织、角色或用户不存在） |
| list_roles | 查询角色 | user_access.manage | 接口或任务 | 无 |
| create_user | 创建用户 | user_access.manage | 接口或任务 | user_access_conflict（组织代码、角色名或用户名已存在）、user_access_missing（组织、角色或用户不存在） |
| list_users | 查询用户 | user_access.manage | 接口或任务 | 无 |
| change_user | 调整用户 | user_access.manage | 接口或任务 | user_access_missing（组织、角色或用户不存在） |
| login | 用户登录 | public | 接口或任务 | login_failed（账号或密码不正确） |
| refresh | 刷新登录 | public | 接口或任务 | refresh_rejected（登录已失效，请重新登录） |
| logout | 退出登录 | public | 接口或任务 | 无 |
| change_password | 修改密码 | signed_in | 接口或任务 | password_mismatch（原密码不正确） |
| purge_sessions | 清理过期刷新令牌 | user_access.system | 接口或任务 | 无 |

## 创建组织（user_access.create_org）

输入 `OrgInput`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| code | str | 是 | 组织代码 |  |  | R-01 |
| name | str | 是 | 组织名称 |  |  | R-01 |

输出 `OrgView`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| code | str | 是 | 组织代码 |  |  | R-01 |
| name | str | 是 | 组织名称 |  |  | R-01 |

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

输入 `Nothing`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |

输出 `OrgList`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| items | list[OrgView] | 是 | 可访问的组织 |  |  |  |

计算流程：

```mermaid
flowchart TD
    start(["输入：无"])
    s1["1. 查询组织（读取）<br/>规则 R-04"]:::read
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

输入 `RoleInput`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| org_id | str | 是 | 角色所属组织代码 |  |  | R-02 |
| name | str | 是 | 角色名称，在组织内唯一 |  |  | R-02 |
| permissions | list[str] | 是 | 角色拥有的权限名 |  |  | R-02 |

输出 `RoleView`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | int | 是 | 角色编号 |  |  |  |
| org_id | str | 是 | 角色所属组织代码 |  |  |  |
| name | str | 是 | 角色名称 |  |  |  |
| permissions | list[str] | 是 | 角色权限 |  |  |  |

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

输入 `OrgQuery`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| org_id | str | 是 | 要查询的组织代码 |  |  | R-04 |

输出 `RoleList`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| items | list[RoleView] | 是 | 可访问的角色 |  |  |  |

计算流程：

```mermaid
flowchart TD
    start(["输入：要查询的组织代码"])
    s1["1. 查询角色（读取）<br/>规则 R-04"]:::read
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

输入 `UserInput`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| org_id | str | 是 | 用户所属组织代码 |  |  | R-02 |
| username | str | 是 | 用户名，在组织内唯一 |  |  | R-02 |
| password | str | 是 | 登录密码 |  |  | R-02 |
| role_id | int | 是 | 角色编号 |  |  | R-02 |

输出 `UserView`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | int | 是 | 用户编号 |  |  |  |
| org_id | str | 是 | 用户所属组织代码 |  |  |  |
| username | str | 是 | 用户名 |  |  |  |
| role_id | int | 是 | 角色编号 |  |  |  |
| active | bool | 是 | 是否允许登录 |  |  |  |

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

输入 `OrgQuery`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| org_id | str | 是 | 要查询的组织代码 |  |  | R-04 |

输出 `UserList`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| items | list[UserView] | 是 | 可访问的用户，不包含密码摘要 |  |  |  |

计算流程：

```mermaid
flowchart TD
    start(["输入：要查询的组织代码"])
    s1["1. 查询用户（读取）<br/>规则 R-04"]:::read
    start --> s1
    finish(["结果：用户列表"])
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
| result | 用户列表 | 步骤 | 查询用户 | R-04 | org_id |

## 调整用户（user_access.change_user）

输入 `UserChange`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| org_id | str | 是 | 用户所属组织代码 |  |  | R-02 |
| user_id | int | 是 | 要修改的用户编号 |  |  |  |
| role_id | int | 是 | 修改后的角色编号 |  |  | R-02 |
| active | bool | 是 | 修改后是否允许登录 |  |  | R-02 |

输出 `UserView`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | int | 是 | 用户编号 |  |  |  |
| org_id | str | 是 | 用户所属组织代码 |  |  |  |
| username | str | 是 | 用户名 |  |  |  |
| role_id | int | 是 | 角色编号 |  |  |  |
| active | bool | 是 | 是否允许登录 |  |  |  |

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

输入 `LoginInput`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| org_code | str | 是 | 组织代码 |  |  | R-03 |
| username | str | 是 | 用户名 |  |  | R-03 |
| password | str | 是 | 密码 |  |  | R-03 |

输出 `SessionGrant`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| account | Account | 是 | 登录的用户及其当前权限 |  |  | R-05 |
| refresh_token | str | 是 | 新的刷新令牌原文，只在这次返回 |  |  | R-05 |
| refresh_expires_at | float | 是 | 刷新令牌失效时间 | Unix 秒 |  | R-05 |

计算流程：

```mermaid
flowchart TD
    start(["输入：组织代码、用户名、密码"])
    s1["1. 校验登录（读取）<br/>规则 R-03"]:::read
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
| account | 经过密码校验的用户 | 步骤 | 校验登录 | R-03 | org_code、username、password |
| result | 新建的登录会话 | 步骤 | 建立登录会话 | R-05 | account |

## 刷新登录（user_access.refresh）

输入 `RefreshInput`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| refresh_token | str | 是 | 刷新令牌 |  |  | R-05 |

输出 `SessionRenewal`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| grant | SessionGrant \| None | 是 | 换得的新会话 |  | 刷新令牌无效、过期、已作废或被重复使用 | R-05 |

计算流程：

```mermaid
flowchart TD
    start(["输入：刷新令牌"])
    s1["1. 核对刷新令牌（读取）<br/>规则 R-05"]:::read
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
| check | 刷新令牌的核对结果 | 步骤 | 核对刷新令牌 | R-05 | refresh_token |
| result | 换得的新会话 | 步骤 | 轮换刷新令牌 | R-05 | check |

## 退出登录（user_access.logout）

输入 `RefreshInput`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| refresh_token | str | 是 | 刷新令牌 |  |  | R-05 |

输出 `Nothing`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |

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

输入 `PasswordChange`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| old_password | str | 是 | 原密码 |  |  | R-06 |
| new_password | str | 是 | 新密码 |  |  | R-06 |

输出 `Nothing`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |

计算流程：

```mermaid
flowchart TD
    start(["输入：原密码、新密码"])
    s1["1. 核对原密码（读取）<br/>规则 R-06"]:::read
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
| user_id | 核对过原密码的用户编号 | 步骤 | 核对原密码 | R-06 | old_password |
| result | 没有返回内容 | 步骤 | 更新密码并作废会话 | R-06 | user_id、new_password |

## 清理过期刷新令牌（user_access.purge_sessions）

输入 `Nothing`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |

输出 `PurgeResult`：

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| removed | int | 是 | 删除的刷新令牌记录数 |  |  | R-07 |

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
