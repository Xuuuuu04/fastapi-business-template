"""
文件管理的公开数据和流程数据。存储键仅供授权后的下载使用。
"""

from datetime import datetime

from shared.public import BusinessError, Data, Kind, Nothing, WorkData, meaning


class SaveInput(Data):
    org_id: str = meaning("文件所属组织", rule="R-02")
    temp_id: str = meaning("上传临时区返回的文件编号", rule="R-01")


class FileQuery(Data):
    org_id: str = meaning("文件所属组织", rule="R-02")
    file_id: str = meaning("文件编号", rule="R-02")


class OrgQuery(Data):
    org_id: str = meaning("要查询的组织", rule="R-02")


class FileView(Data):
    id: str = meaning("文件编号")
    org_id: str = meaning("文件所属组织")
    name: str = meaning("上传时的文件名")
    size: int = meaning("文件大小", unit="字节")
    sha256: str = meaning("文件内容的 SHA-256 摘要")
    content_type: str = meaning("下载响应的内容类型")
    created_at: datetime = meaning("保存时间，UTC")


class FileEntry(Data):
    view: FileView = meaning("经组织权限核对后的文件信息")
    key: str = meaning("正式存储键，只供服务端读取", secret=True)


class FileList(Data):
    items: list[FileView] = meaning("本组织未删除的文件")


class FileStage(Data):
    id: str = meaning("准备保存的文件编号")
    org_id: str = meaning("文件所属组织")
    name: str = meaning("上传时的文件名")
    size: int = meaning("文件大小", unit="字节")
    sha256: str = meaning("文件内容摘要")
    content_type: str = meaning("文件内容类型")
    key: str = meaning("正式存储键", secret=True)


class PendingFile(Data):
    id: str = meaning("已标记删除的文件编号")
    key: str = meaning("需要从存储删除的键", secret=True)


class CleanResult(Data):
    removed: int = meaning("清理的文件记录数", rule="R-03")
    temp_removed: int = meaning("清理的临时文件数", rule="R-03")
    orphan_removed: int = meaning("清理的无记录正式文件数", rule="R-03")


class FileMissing(BusinessError):
    code = "file_missing"
    kind = Kind.NOT_FOUND
    message = "文件不存在或不能访问"


class SaveWork(WorkData):
    org_id: str = meaning("文件所属组织")
    temp_id: str = meaning("临时文件编号")
    staged: FileStage = meaning("已保存到文件存储的内容")
    result: FileView = meaning("保存后的文件信息")


class GetWork(WorkData):
    org_id: str = meaning("文件所属组织")
    file_id: str = meaning("文件编号")
    result: FileEntry = meaning("授权后的文件信息和存储键")


class ListWork(WorkData):
    org_id: str = meaning("要查询的组织")
    result: FileList = meaning("文件列表")


class DeleteWork(WorkData):
    org_id: str = meaning("文件所属组织")
    file_id: str = meaning("要删除的文件编号")
    result: Nothing = meaning("标记删除完成")


class CleanWork(WorkData):
    pending: list[PendingFile] = meaning("待删除的存储文件")
    orphans: list[str] = meaning("超过一小时仍没有文件记录的存储键", secret=True)
    deleted_ids: list[str] = meaning("已从存储删除的文件编号")
    temp_removed: int = meaning("已清理的临时文件数")
    orphan_removed: int = meaning("已清理的无记录正式文件数")
    result: CleanResult = meaning("清理结果")
