# 文件管理（file_library）

## 职责

接收临时上传，登记文件元数据，按组织范围查询、下载和标记删除。每日任务清理已删除文件、过期临时上传，以及超过一小时仍没有文件记录的正式对象。文件内容可保存在本地或 S3 兼容存储。

## 公开操作

| 操作 | 用途 | 权限 |
| --- | --- | --- |
| `file_library.save_file` | 将临时上传保存并登记 | `file_library.write` |
| `file_library.get_file` | 授权后读取文件信息 | `file_library.read` |
| `file_library.list_files` | 查询组织文件 | `file_library.read` |
| `file_library.delete_file` | 标记删除，使下载立即失效 | `file_library.write` |
| `file_library.clean_files` | 清理对象和已删除记录 | `file_library.clean`，仅系统任务 |

## 依赖

使用框架提供的数据库、文件存储、上传临时区和调用者身份；没有其他业务模块依赖。

## 内部组织

- `data.py` 定义输入、输出及流程字段；`flow.py` 连接步骤。
- `steps/files.py` 先处理文件内容，再更新数据库记录。
- `store/sql.py` 检查组织范围并调用模块文件入口；`store/tables.py` 定义文件记录表。

## 业务文档

业务规则和确认样例见 [doc/file_library](../../../doc/file_library/rules.md)。

## 测试

`tests/integration/file_library/` 从 HTTP 入口检查上传、隔离、下载、删除，并触发清理操作。
