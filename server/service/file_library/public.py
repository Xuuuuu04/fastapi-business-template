"""
文件模块对接口和其他模块提供的操作约定与数据。
"""

from service.file_library.data import (
    CleanResult,
    FileEntry,
    FileListQuery,
    FileMissing,
    FilePage,
    FileQuery,
    FileView,
    SaveInput,
)
from shared.public import Nothing, contract

save_file = contract(
    "file_library.save_file",
    "保存上传文件",
    input=SaveInput,
    output=FileView,
    access="file_library.write",
    audit=True,
)
get_file = contract(
    "file_library.get_file",
    "读取文件",
    input=FileQuery,
    output=FileEntry,
    access="file_library.read",
    errors=(FileMissing,),
)
list_files = contract(
    "file_library.list_files",
    "查询文件",
    input=FileListQuery,
    output=FilePage,
    access="file_library.read",
)
delete_file = contract(
    "file_library.delete_file",
    "删除文件",
    input=FileQuery,
    output=Nothing,
    access="file_library.write",
    errors=(FileMissing,),
    audit=True,
)
clean_files = contract(
    "file_library.clean_files",
    "清理已删除文件",
    input=Nothing,
    output=CleanResult,
    access="file_library.clean",
    audit=True,
    timeout=120,
)

__all__ = [
    "CleanResult",
    "FileEntry",
    "FilePage",
    "FileMissing",
    "FileQuery",
    "FileView",
    "FileListQuery",
    "SaveInput",
    "save_file",
    "get_file",
    "list_files",
    "delete_file",
    "clean_files",
]
