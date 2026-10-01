# 单体后端模板 接口清单

由实际路由自动生成。服务密钥放在请求头 X-API-Key。

## GET /health/live

用途：进程是否存活
分组：运行状态
操作编号：health_live

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | object |

## GET /health/ready

用途：是否可以接收请求
分组：运行状态
操作编号：health_ready

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | 未指定 |

## GET /api/system/modules

用途：模块目录和关系图
分组：运行诊断
操作编号：system_modules

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | object |

## GET /api/system/flows/{name}

用途：操作的计算流程
分组：运行诊断
操作编号：system_flow

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| name | path | 是 | string |  |  |

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | object |
| 422 | Validation Error | HTTPValidationError |

## GET /api/system/fields/{name}/{field}

用途：字段来源
分组：运行诊断
操作编号：system_field

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| name | path | 是 | string |  |  |
| field | path | 是 | string |  |  |

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | object |
| 422 | Validation Error | HTTPValidationError |

## GET /api/system/runs

用途：最近的运行
分组：运行诊断
操作编号：system_runs

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| module | query | 否 | string |  |  |
| contract | query | 否 | string |  |  |
| status | query | 否 | string |  |  |
| request_id | query | 否 | string |  |  |
| job_id | query | 否 | string |  |  |
| before | query | 否 | number 或 null |  |  |
| limit | query | 否 | integer | 最小：1；最大：200 |  |

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | object |
| 422 | Validation Error | HTTPValidationError |

## GET /api/system/runs/{run_id}

用途：一次运行的详情
分组：运行诊断
操作编号：system_run

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| run_id | path | 是 | string |  |  |

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | object |
| 422 | Validation Error | HTTPValidationError |

## GET /api/system/runs/{run_id}/report

用途：一次运行的中文诊断报告
分组：运行诊断
操作编号：system_run_report

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| run_id | path | 是 | string |  |  |

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | string |
| 422 | Validation Error | HTTPValidationError |

## GET /api/system/runtime

用途：进程运行状态
分组：运行诊断
操作编号：system_runtime

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | object |

## GET /api/system/stats

用途：运行统计
分组：运行诊断
操作编号：system_stats

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| hours | query | 否 | integer | 最小：1；最大：2160 |  |
| module | query | 否 | string |  |  |

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | object |
| 422 | Validation Error | HTTPValidationError |

## GET /api/jobs/{job_id}

用途：查看任务
分组：后台任务
操作编号：get_job

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| job_id | path | 是 | string |  |  |

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | object |
| 422 | Validation Error | HTTPValidationError |

## GET /api/system/jobs

用途：列出任务
分组：后台任务
操作编号：system_jobs

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| state | query | 否 | string |  |  |
| contract | query | 否 | string |  |  |
| limit | query | 否 | integer | 最小：1；最大：200 |  |

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | object |
| 422 | Validation Error | HTTPValidationError |

## GET /api/system/audit

用途：查询审计记录
分组：安全审计
操作编号：system_audit

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| limit | query | 否 | integer | 最小：1；最大：200 |  |

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | object |
| 422 | Validation Error | HTTPValidationError |

## GET /api/system/changes

用途：查询数据变更历史
分组：安全审计
操作编号：system_changes

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| table | query | 否 | string | 最长：80 | 表名，例如 file_library_files |
| key | query | 否 | string | 最长：80 | 记录编号 |
| limit | query | 否 | integer | 最小：1；最大：200 |  |

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | object |
| 422 | Validation Error | HTTPValidationError |

## POST /api/v1/stream/{name}

用途：执行流式操作
分组：流式操作
操作编号：run_stream

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| name | path | 是 | string |  |  |

请求正文：application/json，模型 object。

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | 未指定 |
| 422 | Validation Error | HTTPValidationError |

## GET /api/v1/access/orgs

用途：查询组织
分组：用户权限
操作编号：list_orgs

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | OrgList |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 422 | 输入不符合要求 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## POST /api/v1/access/orgs

用途：创建组织
分组：用户权限
操作编号：create_org

请求正文：application/json，模型 OrgInput。

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | OrgView |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 409 | user_access_conflict：组织代码、角色名或用户名已存在 | ErrorReply |
| 422 | 输入不符合要求；org_code_invalid：组织代码只能由小写字母、数字和短横线组成，长 3 至 32 字符；名称不能为空 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## POST /api/v1/access/roles

用途：创建角色
分组：用户权限
操作编号：create_role

请求正文：application/json，模型 RoleInput。

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | RoleView |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 404 | user_access_missing：组织、角色或用户不存在 | ErrorReply |
| 409 | user_access_conflict：组织代码、角色名或用户名已存在 | ErrorReply |
| 422 | 输入不符合要求 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## GET /api/v1/access/roles

用途：查询角色
分组：用户权限
操作编号：list_roles

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| org_id | query | 是 | string |  |  |

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | RoleList |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 422 | 输入不符合要求 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## POST /api/v1/access/users

用途：创建用户
分组：用户权限
操作编号：create_user

请求正文：application/json，模型 UserInput。

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | UserView |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 404 | user_access_missing：组织、角色或用户不存在 | ErrorReply |
| 409 | user_access_conflict：组织代码、角色名或用户名已存在 | ErrorReply |
| 422 | 输入不符合要求 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## GET /api/v1/access/users

用途：查询用户
分组：用户权限
操作编号：list_users

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| org_id | query | 是 | string |  | 要查询的组织代码；规则：R-04 |
| after | query | 否 | string | 最长：40 | 上一页返回的 next_after；为空表示：从第一页开始 |
| limit | query | 否 | integer | 最小：1；最大：100 | 本页最多返回多少条 |

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | CursorPage_UserView_ |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 422 | 输入不符合要求 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## PUT /api/v1/access/users

用途：调整用户
分组：用户权限
操作编号：change_user

请求正文：application/json，模型 UserChange。

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | UserView |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 404 | user_access_missing：组织、角色或用户不存在 | ErrorReply |
| 422 | 输入不符合要求 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## POST /api/v1/access/login

用途：用户登录
分组：用户权限
操作编号：login

请求正文：application/json，模型 LoginInput。

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | TokenReply |
| 401 | 没有提供有效身份；login_failed：账号或密码不正确；otp_required：需要两步验证码 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 422 | 输入不符合要求 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## POST /api/v1/access/refresh

用途：刷新登录
分组：用户权限
操作编号：refresh

请求正文：application/json，模型 RefreshInput。

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | TokenReply |
| 401 | 没有提供有效身份；refresh_rejected：登录已失效，请重新登录 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 422 | 输入不符合要求 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## POST /api/v1/access/logout

用途：退出登录
分组：用户权限
操作编号：logout

请求正文：application/json，模型 RefreshInput。

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 204 | Successful Response | 空响应 |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 422 | 输入不符合要求 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## POST /api/v1/access/password

用途：修改密码
分组：用户权限
操作编号：change_password

请求正文：application/json，模型 PasswordChange。

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 204 | Successful Response | 空响应 |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 422 | 输入不符合要求；password_mismatch：原密码不正确 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## POST /api/v1/access/users/reset-code

用途：生成密码重置码
分组：用户权限
操作编号：issue_reset

请求正文：application/json，模型 UserRef。

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | ResetCode |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 422 | 输入不符合要求 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## POST /api/v1/access/password/reset

用途：用重置码设置新密码
分组：用户权限
操作编号：reset_password

请求正文：application/json，模型 ResetInput。

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 204 | Successful Response | 空响应 |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 422 | 输入不符合要求；reset_invalid：重置码无效或已过期 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## POST /api/v1/access/otp

用途：生成两步验证密钥
分组：用户权限
操作编号：start_otp

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | OtpSetup |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 422 | 输入不符合要求；otp_invalid：验证码不正确或已用过 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## POST /api/v1/access/otp/enable

用途：开启两步验证
分组：用户权限
操作编号：enable_otp

请求正文：application/json，模型 OtpCode。

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 204 | Successful Response | 空响应 |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 422 | 输入不符合要求；otp_invalid：验证码不正确或已用过 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## POST /api/v1/access/otp/disable

用途：关闭两步验证
分组：用户权限
操作编号：disable_otp

请求正文：application/json，模型 OtpCode。

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 204 | Successful Response | 空响应 |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 422 | 输入不符合要求；otp_invalid：验证码不正确或已用过 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## POST /api/v1/access/users/otp/reset

用途：管理员关闭两步验证
分组：用户权限
操作编号：reset_otp

请求正文：application/json，模型 UserRef。

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 204 | Successful Response | 空响应 |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 422 | 输入不符合要求 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## POST /api/v1/files/{org_id}

用途：上传文件
分组：文件管理
操作编号：save_file

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| org_id | path | 是 | string |  |  |

请求正文：multipart/form-data，模型 Body_save_file。

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | FileView |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 422 | 输入不符合要求 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## GET /api/v1/files/{org_id}

用途：查询文件
分组：文件管理
操作编号：list_files

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| org_id | path | 是 | string |  |  |
| offset | query | 否 | integer | 最小：0 | 从第几条开始，从 0 计数 |
| limit | query | 否 | integer | 最小：1；最大：100 | 本页最多返回多少条 |

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | Page_FileView_ |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 422 | 输入不符合要求 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## GET /api/v1/files/{org_id}/{file_id}/info

用途：文件信息
分组：文件管理
操作编号：get_file_info

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| org_id | path | 是 | string |  |  |
| file_id | path | 是 | string |  |  |

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | FileView |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 404 | file_missing：文件不存在或不能访问 | ErrorReply |
| 422 | 输入不符合要求 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## GET /api/v1/files/{org_id}/{file_id}/download

用途：下载文件
分组：文件管理
操作编号：download_file

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| org_id | path | 是 | string |  |  |
| file_id | path | 是 | string |  |  |

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | 未指定 |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 404 | file_missing：文件不存在或不能访问 | ErrorReply |
| 422 | 输入不符合要求 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## DELETE /api/v1/files/{org_id}/{file_id}

用途：删除文件
分组：文件管理
操作编号：delete_file

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| org_id | path | 是 | string |  |  |
| file_id | path | 是 | string |  |  |

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 204 | Successful Response | 空响应 |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 404 | file_missing：文件不存在或不能访问 | ErrorReply |
| 422 | 输入不符合要求 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## 数据模型

### Body_save_file

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| upload | string | 是 |  |  |

### CursorPage_UserView_

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| items | 列表[UserView] | 是 | 本页记录 |  |
| next_after | string | 否 | 取下一页时作为 after 传回的位置；为空表示：已经是最后一页 |  |

### ErrorReply

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| code | string | 是 | 稳定的错误码，程序按它判断，不要按说明文字判断 |  |
| kind | string | 是 | 错误种类，例如 invalid、not_found、conflict、temporary |  |
| message | string | 是 | 给人看的中文说明 |  |
| request_id | string | 是 | 请求编号，用于查日志 |  |
| run_id | string | 否 | 运行编号，用于查看执行过程；没有进入业务流程时为空文本 |  |
| fields | 列表[FieldProblem] | 否 | 逐个字段的问题 |  |

### FieldProblem

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| field | string | 是 | 有问题的字段路径，例如 lines.0.quantity |  |
| problem | string | 是 | 问题说明 |  |

### FileView

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| id | string | 是 | 文件编号 |  |
| org_id | string | 是 | 文件所属组织 |  |
| name | string | 是 | 上传时的文件名 |  |
| size | integer | 是 | 文件大小；单位：字节 |  |
| sha256 | string | 是 | 文件内容的 SHA-256 摘要 |  |
| content_type | string | 是 | 下载响应的内容类型 |  |
| created_at | date-time | 是 | 保存时间，UTC |  |

### HTTPValidationError

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| detail | 列表[ValidationError] | 否 |  |  |

### LoginInput

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| org_code | string | 是 | 组织代码；规则：R-03 | 最长：32 |
| username | string | 是 | 用户名；规则：R-03 | 最长：64 |
| password | string | 是 | 密码；规则：R-03 | 最长：256 |
| otp_code | string | 否 | 两步验证码；为空表示：没有开启两步验证；规则：R-09 | 最长：10 |

### OrgInput

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| code | string | 是 | 组织代码；规则：R-01 | 最短：3；最长：32 |
| name | string | 是 | 组织名称；规则：R-01 | 最短：1；最长：80 |

### OrgList

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| items | 列表[OrgView] | 是 | 可访问的组织 |  |

### OrgView

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| code | string | 是 | 组织代码；规则：R-01 |  |
| name | string | 是 | 组织名称；规则：R-01 |  |

### OtpCode

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| code | string | 是 | 身份验证器应用显示的 6 位验证码；规则：R-09 | 最短：6；最长：6 |

### OtpSetup

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| secret | string | 是 | 两步验证密钥，填进身份验证器应用；规则：R-09 |  |
| uri | string | 是 | 可生成二维码的地址；规则：R-09 |  |

### Page_FileView_

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| items | 列表[FileView] | 是 | 本页记录 |  |
| total | integer | 是 | 符合条件的记录总数 |  |
| offset | integer | 是 | 本页从第几条开始，从 0 计数 |  |
| limit | integer | 是 | 本页最多返回多少条 |  |

### PasswordChange

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| old_password | string | 是 | 原密码；规则：R-06 | 最长：256 |
| new_password | string | 是 | 新密码；规则：R-06 | 最短：8；最长：256 |

### RefreshInput

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| refresh_token | string | 是 | 刷新令牌；规则：R-05 | 最短：20；最长：200 |

### ResetCode

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| code | string | 是 | 一次性重置码，只返回这一次；规则：R-08 |  |
| expires_in | integer | 是 | 还有多少秒失效；单位：秒；规则：R-08 |  |

### ResetInput

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| org_code | string | 是 | 组织代码；规则：R-08 | 最长：32 |
| username | string | 是 | 用户名；规则：R-08 | 最长：64 |
| code | string | 是 | 管理员给的重置码；规则：R-08 | 最长：64 |
| new_password | string | 是 | 新密码；规则：R-08 | 最短：8；最长：256 |

### RoleInput

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| org_id | string | 是 | 角色所属组织代码；规则：R-02 |  |
| name | string | 是 | 角色名称，在组织内唯一；规则：R-02 | 最短：1；最长：64 |
| permissions | 列表[string] | 是 | 角色拥有的权限名；规则：R-02 |  |

### RoleList

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| items | 列表[RoleView] | 是 | 可访问的角色 |  |

### RoleView

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| id | integer | 是 | 角色编号 |  |
| org_id | string | 是 | 角色所属组织代码 |  |
| name | string | 是 | 角色名称 |  |
| permissions | 列表[string] | 是 | 角色权限 |  |

### TokenReply

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| access_token | string | 是 | 访问令牌，请求时放在 Authorization: Bearer 后面 |  |
| token_type | string | 否 | 令牌类型，固定为 Bearer |  |
| expires_in | integer | 是 | 访问令牌还有多少秒失效 |  |
| refresh_token | string | 是 | 刷新令牌，只用于换新令牌和退出登录，每次刷新后换新 |  |
| refresh_expires_in | integer | 是 | 刷新令牌还有多少秒失效 |  |
| user_id | integer | 是 | 用户编号 |  |
| org_id | string | 是 | 用户所属组织 |  |

### UserChange

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| org_id | string | 是 | 用户所属组织代码；规则：R-02 |  |
| user_id | integer | 是 | 要修改的用户编号 | 大于：0.0 |
| role_id | integer | 是 | 修改后的角色编号；规则：R-02 | 大于：0.0 |
| active | boolean | 是 | 修改后是否允许登录；规则：R-02 |  |

### UserInput

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| org_id | string | 是 | 用户所属组织代码；规则：R-02 |  |
| username | string | 是 | 用户名，在组织内唯一；规则：R-02 | 最短：1；最长：64 |
| password | string | 是 | 登录密码；规则：R-02 | 最短：8；最长：256 |
| role_id | integer | 是 | 角色编号；规则：R-02 | 大于：0.0 |

### UserRef

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| org_id | string | 是 | 用户所属组织代码；规则：R-04 | 最长：32 |
| user_id | integer | 是 | 用户编号 | 大于：0.0 |

### UserView

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| id | integer | 是 | 用户编号 |  |
| org_id | string | 是 | 用户所属组织代码 |  |
| username | string | 是 | 用户名 |  |
| role_id | integer | 是 | 角色编号 |  |
| active | boolean | 是 | 是否允许登录 |  |

### ValidationError

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| loc | 列表[string 或 integer] | 是 |  |  |
| msg | string | 是 |  |  |
| type | string | 是 |  |  |
| input | 未指定 | 否 |  |  |
| ctx | object | 否 |  |  |

