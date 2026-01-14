
-- 平台信息表
CREATE TABLE IF NOT EXISTS platforms (
    id TEXT PRIMARY KEY,
    name TEXT,
    updated_at TEXT
);

-- 新闻条目主表
CREATE TABLE IF NOT EXISTS news_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    platform_id TEXT,
    rank INTEGER,
    url TEXT,
    mobile_url TEXT,
    image_url TEXT DEFAULT '',
    first_crawl_time TEXT,
    last_crawl_time TEXT,
    crawl_count INTEGER DEFAULT 1,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (platform_id) REFERENCES platforms(id)
);

-- 标题变更历史
CREATE TABLE IF NOT EXISTS title_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    news_item_id INTEGER,
    old_title TEXT,
    new_title TEXT,
    changed_at TEXT,
    FOREIGN KEY (news_item_id) REFERENCES news_items(id)
);

-- 排名历史记录
CREATE TABLE IF NOT EXISTS rank_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    news_item_id INTEGER,
    rank INTEGER,
    crawl_time TEXT,
    created_at TEXT,
    FOREIGN KEY (news_item_id) REFERENCES news_items(id)
);

-- 抓取批次记录
CREATE TABLE IF NOT EXISTS crawl_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crawl_time TEXT UNIQUE,
    total_items INTEGER,
    created_at TEXT
);

-- 抓取来源状态记录
CREATE TABLE IF NOT EXISTS crawl_source_status (
    crawl_record_id INTEGER,
    platform_id TEXT,
    status TEXT,
    PRIMARY KEY (crawl_record_id, platform_id),
    FOREIGN KEY (crawl_record_id) REFERENCES crawl_records(id),
    FOREIGN KEY (platform_id) REFERENCES platforms(id)
);

-- 已推送新闻记录 (常位于 history.db)
CREATE TABLE IF NOT EXISTS pushed_news (
    content_hash TEXT PRIMARY KEY,
    title TEXT,
    url TEXT,
    pushed_at TEXT
);

-- 推送任务执行记录
CREATE TABLE IF NOT EXISTS push_records (
    date TEXT PRIMARY KEY,
    pushed INTEGER,
    push_time TEXT,
    report_type TEXT,
    created_at TEXT
);
