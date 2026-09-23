"""
文件管理模块的操作、存储实现、表和每日清理任务。
"""

from datetime import time

from service.file_library import flow, public
from service.file_library.store.sql import SqlFileStore
from service.file_library.store.tables import files
from shared.public import JobPlan, Module, Nothing, Retry, Schedule

module = Module(
    name="file_library",
    title="文件管理",
    version="1",
    provides={
        public.save_file: flow.save_file,
        public.get_file: flow.get_file,
        public.list_files: flow.list_files,
        public.delete_file: flow.delete_file,
        public.clean_files: flow.clean_files,
    },
    store=SqlFileStore,
    tables=(files,),
    jobs=(JobPlan(public.clean_files, retry=Retry(times=2), repeat_safe=True, max_queued=10),),
    schedules=(
        Schedule(
            name="clean_files_daily",
            title="每天清理已删除文件、过期上传和孤立文件",
            contract=public.clean_files,
            input=Nothing(),
            daily_at=time(3, 0),
        ),
    ),
)
