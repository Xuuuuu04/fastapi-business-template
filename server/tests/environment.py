"""
测试子进程只继承系统运行所需变量，不携带模型、业务系统或其他应用的凭据。
"""

import os

SYSTEM_KEYS = {
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "TMPDIR",
    "TMP",
    "TEMP",
    "LANG",
    "TZ",
    "SYSTEMROOT",
    "WINDIR",
    "PYTHONPATH",
    "PYTHONUNBUFFERED",
    "PYTHONDONTWRITEBYTECODE",
    "UV_CACHE_DIR",
    "TEMPLATE_COPY_RUN",
}


# 测试地址由调用方另外明确加入，不在系统变量里搜索其他可用凭据。
def subprocess_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key in SYSTEM_KEYS or key.startswith("LC_")
    }
