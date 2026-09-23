/*
建立笔记示例表。
标题唯一，时间保存为带时区的 UTC 文本。
*/
BEGIN IMMEDIATE;
CREATE TABLE notes (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL UNIQUE CHECK (length(title) BETWEEN 1 AND 80),
    body TEXT NOT NULL CHECK (length(body) <= 5000),
    created_at TEXT NOT NULL
);
PRAGMA user_version = 1;
COMMIT;
