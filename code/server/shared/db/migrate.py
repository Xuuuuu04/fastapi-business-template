"""
执行当前 SQLite 初始迁移。
重复执行不会清空数据，应用启动不会自动修改表结构。
"""

from pathlib import Path

from shared.config.settings import Settings
from shared.db.connect import connect


# 将空数据库升级到当前结构版本。
def migrate(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version == 1:
            return
        if version != 0:
            raise RuntimeError("数据库版本不受当前程序支持")
        source = Path(__file__).parent / "migrations" / "001_notes.sql"
        conn.executescript(source.read_text(encoding="utf-8"))
    finally:
        conn.close()


# 读取配置并执行数据库迁移。
def main() -> None:
    migrate(Settings().db_path)
    print("数据库结构已就绪。")


if __name__ == "__main__":
    main()
