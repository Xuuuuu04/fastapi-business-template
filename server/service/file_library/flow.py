"""
文件管理操作的步骤顺序。
"""

from service.file_library.data import CleanWork, DeleteWork, GetWork, ListWork, SaveWork
from service.file_library.steps import files
from shared.public import Flow

save_file = Flow(
    "保存上传文件", work=SaveWork, result="result", steps=[files.prepare_file, files.save_file]
)
get_file = Flow("读取文件", work=GetWork, result="result", steps=[files.read_file])
list_files = Flow("查询文件", work=ListWork, result="result", steps=[files.list_files])
delete_file = Flow("删除文件", work=DeleteWork, result="result", steps=[files.delete_file])
clean_files = Flow(
    "清理已删除文件",
    work=CleanWork,
    result="result",
    steps=[files.find_deleted, files.remove_objects, files.delete_rows],
)
