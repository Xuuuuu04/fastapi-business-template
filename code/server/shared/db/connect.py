"""
管理 SQLite 连接与结构版本检查。
每个请求独立使用连接，表结构通过迁移命令建立。
"""

import sqlite3
from pathlib import Path


# 打开独立连接并启用行字段访问。
def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=5, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# 检查数据库文件和笔记表是否完成初始化。
def ready(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        conn = connect(path)
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            conn.execute("SELECT id, title, body, created_at FROM notes LIMIT 0")
            return version == 1
        finally:
            conn.close()
    except sqlite3.Error:
        return False
