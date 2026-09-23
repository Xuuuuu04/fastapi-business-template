# 用户权限：需求

本模块给采用模板的项目提供组织、角色和用户的基础管理。系统管理员创建组织，组织管理员在自己的组织内建立角色、创建用户并调整状态；用户用组织代码、用户名和密码登录。其他业务模块通过经过验证的调用者身份取得组织编号与权限。

这些是通用模板的默认规则，具体项目使用前需核对组织划分、角色名称和权限集合。

| 功能 | 操作 |
| --- | --- |
| 创建和查询组织 | `user_access.create_org`、`user_access.list_orgs` |
| 创建和查询角色 | `user_access.create_role`、`user_access.list_roles` |
| 创建、查询、停用用户和调整角色 | `user_access.create_user`、`user_access.list_users`、`user_access.change_user` |
| 用户登录 | `user_access.login` |

不包含找回密码、单点登录和跨组织兼任。项目需要时在业务规则确认后扩展。
