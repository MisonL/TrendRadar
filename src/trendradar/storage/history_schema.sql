-- 推送记录表
CREATE TABLE IF NOT EXISTS push_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_type TEXT NOT NULL,
    date TEXT NOT NULL,
    push_time TEXT NOT NULL,
    pushed INTEGER DEFAULT 1,
    created_at TEXT,
    UNIQUE(date, report_type)
);

-- 新闻推送明细表 (用于去重)
-- table name matches local.py: pushed_news
CREATE TABLE IF NOT EXISTS pushed_news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT NOT NULL,
    title TEXT,
    url TEXT,
    pushed_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(content_hash)
);

-- 索引提升查询速度
CREATE INDEX IF NOT EXISTS idx_pushed_news_hash ON pushed_news(content_hash);
CREATE INDEX IF NOT EXISTS idx_push_records_date ON push_records(date);
