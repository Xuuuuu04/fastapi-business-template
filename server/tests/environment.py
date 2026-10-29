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


def subprocess_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key in SYSTEM_KEYS or key.startswith("LC_")
    }
