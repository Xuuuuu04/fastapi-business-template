# FastAPI 通用后端模板 接口清单

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
分组：运行排查
操作编号：system_modules

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | object |

## GET /api/system/flows/{name}

用途：操作的计算流程
分组：运行排查
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
分组：运行排查
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
分组：运行排查
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
分组：运行排查
操作编号：system_run

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| run_id | path | 是 | string |  |  |

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | object |
| 422 | Validation Error | HTTPValidationError |

## GET /api/system/runs/{run_id}/report

用途：一次运行的中文排查报告
分组：运行排查
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
分组：运行排查
操作编号：system_runtime

| 状态码 | 含义 | 返回模型 |
| --- | --- | --- |
| 200 | Successful Response | object |

## GET /api/system/stats

用途：运行统计
分组：运行排查
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

用途：查询操作记录
分组：安全操作记录
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
分组：安全操作记录
操作编号：system_changes

| 参数 | 位置 | 必填 | 类型 | 限制 | 说明 |
| --- | --- | --- | --- | --- | --- |
| table | query | 否 | string | 最长：80 | 表名，例如 customer_contact_records |
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

## 数据模型

### HTTPValidationError

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| detail | 列表[ValidationError] | 否 |  |  |

### ValidationError

| 字段 | 类型 | 必填 | 说明 | 限制 |
| --- | --- | --- | --- | --- |
| loc | 列表[string 或 integer] | 是 |  |  |
| msg | string | 是 |  |  |
| type | string | 是 |  |  |
| input | 未指定 | 否 |  |  |
| ctx | object | 否 |  |  |

