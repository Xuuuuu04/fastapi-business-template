# 文件管理：操作与流程

> 本文件由 `uv run python -m tools.export_docs` 根据代码中的声明生成，不要手工修改；业务含义写在 needs.md 和 rules.md。

模块 `file_library`，版本 1。调用的其他模块：无。

## 公开操作

| 操作 | 名称 | 权限 | 接口 | 可能的业务错误 |
| --- | --- | --- | --- | --- |
| save_file | 保存上传文件 | file_library.write | POST /api/v1/files/{org_id} | 无 |
| get_file | 读取文件 | file_library.read | GET /api/v1/files/{org_id}/{file_id}/info<br/>GET /api/v1/files/{org_id}/{file_id}/download | file_missing（文件不存在或不能访问） |
| list_files | 查询文件 | file_library.read | GET /api/v1/files/{org_id} | 无 |
| delete_file | 删除文件 | file_library.write | DELETE /api/v1/files/{org_id}/{file_id} | file_missing（文件不存在或不能访问） |
| clean_files | 清理已删除文件 | file_library.clean | 定时计划 | 无 |

## 保存上传文件（file_library.save_file）

输入 `SaveInput`，输出 `FileView`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：文件所属组织、上传临时区返回的文件编号"])
    s1["1. 保存文件内容（数据访问）<br/>规则 R-01"]:::read
    start --> s1
    s2["2. 登记文件（保存）<br/>规则 R-01"]:::save
    s1 --> s2
    finish(["结果：保存后的文件信息"])
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
| org_id | 文件所属组织 | 操作输入 |  |  |  |
| temp_id | 临时文件编号 | 操作输入 |  |  |  |
| staged | 已保存到文件存储的内容 | 步骤 | 保存文件内容 | R-01 | org_id、temp_id |
| result | 保存后的文件信息 | 步骤 | 登记文件 | R-01 | staged |

## 读取文件（file_library.get_file）

输入 `FileQuery`，输出 `FileEntry`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：文件所属组织、文件编号"])
    s1["1. 读取文件（数据访问）<br/>规则 R-02"]:::read
    start --> s1
    finish(["结果：授权后的文件信息和存储键"])
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
| org_id | 文件所属组织 | 操作输入 |  |  |  |
| file_id | 文件编号 | 操作输入 |  |  |  |
| result | 授权后的文件信息和存储键 | 步骤 | 读取文件 | R-02 | org_id、file_id |

## 查询文件（file_library.list_files）

输入 `FileListQuery`，输出 `Page[FileView]`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：要查询的组织、从第几条开始，从 0 计数、本页最多返回多少条"])
    s1["1. 查询文件（数据访问）<br/>规则 R-02"]:::read
    start --> s1
    finish(["结果：一页文件，按保存时间从新到旧"])
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
| offset | 从第几条开始 | 操作输入 |  |  |  |
| limit | 本页最多返回多少条 | 操作输入 |  |  |  |
| result | 一页文件，按保存时间从新到旧 | 步骤 | 查询文件 | R-02 | org_id、offset、limit |

## 删除文件（file_library.delete_file）

输入 `FileQuery`，输出 `Nothing`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：文件所属组织、文件编号"])
    s1["1. 标记删除（保存）<br/>规则 R-03"]:::save
    start --> s1
    finish(["结果：标记删除完成"])
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
| org_id | 文件所属组织 | 操作输入 |  |  |  |
| file_id | 要删除的文件编号 | 操作输入 |  |  |  |
| result | 标记删除完成 | 步骤 | 标记删除 | R-03 | org_id、file_id |

## 清理已删除文件（file_library.clean_files）

输入 `Nothing`，输出 `CleanResult`，字段见“数据模型”。

计算流程：

```mermaid
flowchart TD
    start(["输入：无"])
    s1["1. 查找待清理文件（数据访问）<br/>规则 R-03"]:::read
    start --> s1
    s2["2. 清理文件内容（数据访问）<br/>规则 R-03"]:::read
    s1 --> s2
    s3["3. 清理文件记录（保存）<br/>规则 R-03"]:::save
    s2 --> s3
    finish(["结果：清理结果"])
    s3 --> finish
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
| pending | 待删除的存储文件 | 步骤 | 查找待清理文件 | R-03 |  |
| orphans | 超过一小时仍没有文件记录的存储键 | 步骤 | 查找待清理文件 | R-03 |  |
| deleted_ids | 已从存储删除的文件编号 | 步骤 | 清理文件内容 | R-03 | pending、orphans |
| temp_removed | 已清理的临时文件数 | 步骤 | 清理文件内容 | R-03 | pending、orphans |
| orphan_removed | 已清理的无记录正式文件数 | 步骤 | 清理文件内容 | R-03 | pending、orphans |
| result | 清理结果 | 步骤 | 清理文件记录 | R-03 | deleted_ids、temp_removed、orphan_removed |

## 数据模型

### SaveInput

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| org_id | str | 是 | 文件所属组织 |  |  | R-02 |
| temp_id | str | 是 | 上传临时区返回的文件编号 |  |  | R-01 |

### FileView

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| id | str | 是 | 文件编号 |  |  |  |
| org_id | str | 是 | 文件所属组织 |  |  |  |
| name | str | 是 | 上传时的文件名 |  |  |  |
| size | int | 是 | 文件大小 | 字节 |  |  |
| sha256 | str | 是 | 文件内容的 SHA-256 摘要 |  |  |  |
| content_type | str | 是 | 下载响应的内容类型 |  |  |  |
| created_at | datetime | 是 | 保存时间，UTC |  |  |  |

### FileQuery

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| org_id | str | 是 | 文件所属组织 |  |  | R-02 |
| file_id | str | 是 | 文件编号 |  |  | R-02 |

### FileEntry

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| view | FileView | 是 | 经组织权限检查后的文件信息 |  |  |  |
| key | str | 是 | 正式存储键，只供服务端读取 |  |  |  |

### FileListQuery

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| org_id | str | 是 | 要查询的组织 |  |  | R-02 |
| offset | int | 否 | 从第几条开始，从 0 计数 |  |  |  |
| limit | int | 否 | 本页最多返回多少条 |  |  |  |

### Page[FileView]

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| items | list[FileView] | 是 | 本页记录 |  |  |  |
| total | int | 是 | 符合条件的记录总数 |  |  |  |
| offset | int | 是 | 本页从第几条开始，从 0 计数 |  |  |  |
| limit | int | 是 | 本页最多返回多少条 |  |  |  |

### Nothing

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |

### CleanResult

| 字段 | 类型 | 必填 | 含义 | 单位 | 为空表示 | 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| removed | int | 是 | 清理的文件记录数 |  |  | R-03 |
| temp_removed | int | 是 | 清理的临时文件数 |  |  | R-03 |
| orphan_removed | int | 是 | 清理的无记录正式文件数 |  |  | R-03 |

## 数据表

### file_library_files

| 列 | 类型 | 可空 | 主键 | 索引 |
| --- | --- | --- | --- | --- |
| id | VARCHAR(32) |  | 是 |  |
| org_id | VARCHAR(64) |  |  | 是 |
| name | VARCHAR(200) |  |  |  |
| size | BIGINT |  |  |  |
| sha256 | VARCHAR(64) |  |  |  |
| content_type | VARCHAR(120) |  |  |  |
| storage_key | VARCHAR(300) |  |  |  |
| created_at | DATETIME |  |  |  |
| deleted_at | FLOAT | 是 |  |  |
