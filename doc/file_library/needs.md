# 文件管理：需求

本模块提供有组织范围的附件上传、查询、下载和删除。上传先进入临时区并检查大小与扩展名，保存操作登记文件元数据；下载前查询文件记录和调用者组织。底层可使用本地目录或 S3 兼容对象存储。

| 功能 | 操作 |
| --- | --- |
| 保存上传 | `file_library.save_file` |
| 查询和下载前授权 | `file_library.get_file`、`file_library.list_files` |
| 标记删除 | `file_library.delete_file` |
| 清理已删除文件 | `file_library.clean_files` |

模板默认文件类型和大小由配置指定。病毒扫描、预览和公开分享链接需要具体项目确认后扩展。
