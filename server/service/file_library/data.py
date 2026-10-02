"""
文件管理的公开数据和流程数据。存储键仅供授权后的下载使用。
"""

from datetime import datetime

from shared.public import BusinessError, Data, Kind, Nothing, Page, WorkData, meaning


# 保存文件的公开输入，指定所属组织和上传临时编号。
class SaveInput(Data):
    org_id: str = meaning("文件所属组织", rule="R-02")
    temp_id: str = meaning("上传临时区返回的文件编号", rule="R-01")


# 查询一个文件的公开输入，必须同时给出组织和文件编号。
class FileQuery(Data):
    org_id: str = meaning("文件所属组织", rule="R-02")
    file_id: str = meaning("文件编号", rule="R-02")


# 组织文件列表的分页条件，限制单页数量。
class FileListQuery(Data):
    org_id: str = meaning("要查询的组织", rule="R-02")
    offset: int = meaning("从第几条开始，从 0 计数", default=0, ge=0)
    limit: int = meaning("本页最多返回多少条", default=20, ge=1, le=100)


# 可返回给调用方的文件信息，包含名称、大小和内容摘要。
class FileView(Data):
    id: str = meaning("文件编号")
    org_id: str = meaning("文件所属组织")
    name: str = meaning("上传时的文件名")
    size: int = meaning("文件大小", unit="字节")
    sha256: str = meaning("文件内容的 SHA-256 摘要")
    content_type: str = meaning("下载响应的内容类型")
    created_at: datetime = meaning("保存时间，UTC")


# 通过组织权限检查后的文件信息与内部存储键，供下载使用。
class FileEntry(Data):
    view: FileView = meaning("经组织权限检查后的文件信息")
    key: str = meaning("正式存储键，只供服务端读取", secret=True)


FilePage = Page[FileView]


# 内容已放入正式存储、尚待写入数据库的文件信息。
class FileStage(Data):
    id: str = meaning("准备保存的文件编号")
    org_id: str = meaning("文件所属组织")
    name: str = meaning("上传时的文件名")
    size: int = meaning("文件大小", unit="字节")
    sha256: str = meaning("文件内容摘要")
    content_type: str = meaning("文件内容类型")
    key: str = meaning("正式存储键", secret=True)


# 已标记删除的文件及存储键，供系统清理任务使用。
class PendingFile(Data):
    id: str = meaning("已标记删除的文件编号")
    key: str = meaning("需要从存储删除的键", secret=True)


# 清理任务的结果，分别统计记录、临时上传和无记录对象。
class CleanResult(Data):
    removed: int = meaning("清理的文件记录数", rule="R-03")
    temp_removed: int = meaning("清理的临时文件数", rule="R-03")
    orphan_removed: int = meaning("清理的无记录正式文件数", rule="R-03")


# 表示“文件不存在或不能访问”的失败，由统一错误入口返回给调用方。
class FileMissing(BusinessError):
    code = "file_missing"
    kind = Kind.NOT_FOUND
    message = "文件不存在或不能访问"


# 保存文件过程中各步骤共享的数据，从临时上传到正式文件记录。
class SaveWork(WorkData):
    org_id: str = meaning("文件所属组织")
    temp_id: str = meaning("临时文件编号")
    staged: FileStage = meaning("已保存到文件存储的内容")
    result: FileView = meaning("保存后的文件信息")


# 读取文件过程中共享的数据，保存组织条件和授权后的文件信息。
class GetWork(WorkData):
    org_id: str = meaning("文件所属组织")
    file_id: str = meaning("文件编号")
    result: FileEntry = meaning("授权后的文件信息和存储键")


# 文件分页查询过程中共享的条件与结果。
class ListWork(WorkData):
    org_id: str = meaning("要查询的组织")
    offset: int = meaning("从第几条开始")
    limit: int = meaning("本页最多返回多少条")
    result: FilePage = meaning("一页文件，按保存时间从新到旧")


# 标记文件删除过程中共享的组织条件和执行结果。
class DeleteWork(WorkData):
    org_id: str = meaning("文件所属组织")
    file_id: str = meaning("要删除的文件编号")
    result: Nothing = meaning("标记删除完成")


# 系统清理过程中共享的待删对象、已删除编号和统计结果。
class CleanWork(WorkData):
    pending: list[PendingFile] = meaning("待删除的存储文件")
    orphans: list[str] = meaning("超过一小时仍没有文件记录的存储键", secret=True)
    deleted_ids: list[str] = meaning("已从存储删除的文件编号")
    temp_removed: int = meaning("已清理的临时文件数")
    orphan_removed: int = meaning("已清理的无记录正式文件数")
    result: CleanResult = meaning("清理结果")
