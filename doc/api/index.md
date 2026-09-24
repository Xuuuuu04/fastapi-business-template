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
| table | query | 否 | string | 最长：80 | 表名，例如 product_catalog_products |
| key | query | 否 | string | 最长：80 | 记录编号 |
| limit | query | 否 | integer | 最小：1；最大：200 |  |

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | object |
| 422 | Validation Error | HTTPValidationError |

## GET /api/v1/products

用途：查询商品
分组：商品目录
操作编号：list_products

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| offset | query | 否 | integer | 最小：0 | 从第几条开始，从 0 计数 |
| limit | query | 否 | integer | 最小：1；最大：100 | 本页最多返回多少条 |
| on_sale | query | 否 | boolean 或 null |  | 只看在售或只看停售；为空表示：不按在售状态筛选 |

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | Page_ProductView_ |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 422 | 输入不符合要求 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## POST /api/v1/products

用途：新建商品
分组：商品目录
操作编号：create_product

请求正文：application/json，模型 ProductInput。

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 201 | Successful Response | ProductView |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 409 | product_code_used：商品编码已被其他商品使用 | ErrorReply |
| 422 | 输入不符合要求 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## POST /api/v1/products/import

用途：批量导入商品
分组：商品目录
操作编号：import_products

请求正文：multipart/form-data，模型 Body_import_products。

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | ImportResult |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 422 | 输入不符合要求 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## GET /api/v1/products/export

用途：导出商品
分组：商品目录
操作编号：export_products

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| on_sale | query | 否 | boolean 或 null |  | 只导出在售或停售，不写则全部导出 |
| format | query | 否 | string | 可选值：['csv', 'xlsx'] | csv 或 xlsx |

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | 未指定 |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 422 | 输入不符合要求 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## GET /api/v1/products/{product_id}

用途：读取商品
分组：商品目录
操作编号：get_product

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| product_id | path | 是 | integer | 大于：0 | 商品编号 |

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | ProductView |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 404 | product_missing：商品不存在 | ErrorReply |
| 422 | 输入不符合要求 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## PUT /api/v1/products/{product_id}

用途：修改商品
分组：商品目录
操作编号：update_product

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| product_id | path | 是 | integer | 大于：0 | 商品编号 |

请求正文：application/json，模型 ProductInput。

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | ProductView |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 404 | product_missing：商品不存在 | ErrorReply |
| 409 | product_code_used：商品编码已被其他商品使用 | ErrorReply |
| 422 | 输入不符合要求 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## DELETE /api/v1/products/{product_id}

用途：删除商品
分组：商品目录
操作编号：delete_product

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| product_id | path | 是 | integer | 大于：0 | 商品编号 |

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 204 | Successful Response | 空响应 |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 404 | product_missing：商品不存在 | ErrorReply |
| 422 | 输入不符合要求 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## POST /api/v1/quotes

用途：创建报价
分组：订单报价
操作编号：create_quote

请求正文：application/json，模型 QuoteRequest。

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 201 | Successful Response | QuoteView |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 422 | 输入不符合要求；nothing_to_quote：所有商品都不能报价：不存在、已停售或尚未定价 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## GET /api/v1/quotes/{quote_id}

用途：读取报价
分组：订单报价
操作编号：get_quote

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| quote_id | path | 是 | integer | 大于：0 | 报价编号 |

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | QuoteView |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 404 | quote_missing：报价不存在 | ErrorReply |
| 422 | 输入不符合要求 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

## POST /api/v1/quotes/expire

用途：标记过期报价（后台任务）
分组：订单报价
操作编号：expire_quotes

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| idempotency-key | header | 否 | string | 最长：120 | 请求编号，重复提交时用来识别同一个请求 |

请求正文：application/json，模型 ExpireRequest。

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 202 | Successful Response | JobAccepted |
| 401 | 没有提供有效身份 | ErrorReply |
| 403 | 没有权限 | ErrorReply |
| 422 | 输入不符合要求 | ErrorReply |
| 500 | 程序与声明不一致，需要修改代码 | ErrorReply |
| 503 | 暂时故障，可以稍后重试 | ErrorReply |

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
| 401 | 没有提供有效身份；login_failed：账号或密码不正确 | ErrorReply |
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

## 数据模型

### Body_import_products

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| upload | string | 是 | CSV（UTF-8）或 .xlsx 文件 |  |

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

### ExpireRequest

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| days | integer | 否 | 创建超过多少天的有效报价标为过期；规则：R-06 | 最小：1.0；最大：3650.0 |

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

### ImportResult

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| created | integer | 是 | 新建的商品数；规则：R-03 |  |
| updated | integer | 是 | 修改的商品数；规则：R-03 |  |
| problems | 列表[RowProblem] | 是 | 没有导入的行及原因；规则：R-03 |  |

### JobAccepted

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| job_id | string | 是 | 任务编号 |  |
| state | string | 是 | 任务状态，刚受理时为 queued |  |
| status_url | string | 是 | 查询任务状态的地址 |  |

### LoginInput

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| org_code | string | 是 | 组织代码；规则：R-03 | 最长：32 |
| username | string | 是 | 用户名；规则：R-03 | 最长：64 |
| password | string | 是 | 密码；规则：R-03 | 最长：256 |

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

### Page_FileView_

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| items | 列表[FileView] | 是 | 本页记录 |  |
| total | integer | 是 | 符合条件的记录总数 |  |
| offset | integer | 是 | 本页从第几条开始，从 0 计数 |  |
| limit | integer | 是 | 本页最多返回多少条 |  |

### Page_ProductView_

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| items | 列表[ProductView] | 是 | 本页记录 |  |
| total | integer | 是 | 符合条件的记录总数 |  |
| offset | integer | 是 | 本页从第几条开始，从 0 计数 |  |
| limit | integer | 是 | 本页最多返回多少条 |  |

### PasswordChange

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| old_password | string | 是 | 原密码；规则：R-06 | 最长：256 |
| new_password | string | 是 | 新密码；规则：R-06 | 最短：8；最长：256 |

### ProductInput

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| code | string | 是 | 商品编码，保存前去掉首尾空白并转成大写；规则：R-01 | 最短：1；最长：40 |
| name | string | 是 | 商品名称 | 最短：1；最长：80 |
| price | number 或 string 或 null | 否 | 单价；单位：元；为空表示：尚未定价，不能用于报价；规则：R-02 |  |
| on_sale | boolean | 否 | 是否在售；停售的商品不能用于报价；规则：R-02 |  |

### ProductView

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| id | integer | 是 | 商品编号 |  |
| code | string | 是 | 商品编码；规则：R-01 |  |
| name | string | 是 | 商品名称 |  |
| price | string 或 null | 是 | 单价；单位：元；为空表示：尚未定价；规则：R-02 |  |
| on_sale | boolean | 是 | 是否在售；规则：R-02 |  |
| updated_at | date-time | 是 | 最后修改时间（UTC） |  |

### QuoteLine

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| code | string | 是 | 商品编码 |  |
| quantity | integer | 是 | 数量；同一编码的多行已合并；规则：R-01 |  |
| unit_price | string | 是 | 单价；单位：元；规则：R-02 |  |
| amount | string | 是 | 金额 = 单价 × 数量；单位：元；规则：R-02 |  |

### QuoteLineInput

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| code | string | 是 | 商品编码 | 最短：1；最长：40 |
| quantity | integer | 是 | 数量 | 最小：1.0；最大：10000.0 |

### QuoteRequest

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| customer | string | 是 | 客户名称 | 最短：1；最长：80 |
| member_level | string | 是 | 会员等级：none 非会员，silver 银卡，gold 金卡；规则：R-03 | 可选值：['none', 'silver', 'gold'] |
| lines | 列表[QuoteLineInput] | 是 | 报价明细 |  |

### QuoteView

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| id | integer | 是 | 报价编号 |  |
| customer | string | 是 | 客户名称 |  |
| member_level | string | 是 | 会员等级；规则：R-03 | 可选值：['none', 'silver', 'gold'] |
| lines | 列表[QuoteLine] | 是 | 计入报价的明细；规则：R-02 |  |
| excluded | 列表[string] | 是 | 没有计入报价的商品编码：不存在、停售或未定价；规则：R-02 |  |
| subtotal | string | 是 | 商品合计；单位：元；规则：R-02 |  |
| discount | string | 是 | 会员优惠；单位：元；规则：R-03 |  |
| total | string | 是 | 应付金额；单位：元；规则：R-04 |  |
| explanation | string | 是 | 给客户看的报价说明，由大模型生成；规则：R-05 |  |
| status | string | 是 | 报价状态：active 有效，expired 已过期；规则：R-06 | 可选值：['active', 'expired'] |
| created_at | date-time | 是 | 创建时间（UTC） |  |

### RefreshInput

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| refresh_token | string | 是 | 刷新令牌；规则：R-05 | 最短：20；最长：200 |

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

### RowProblem

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| row | integer | 是 | 行号；规则：R-03 |  |
| message | string | 是 | 这一行没有导入的原因；规则：R-03 |  |

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

