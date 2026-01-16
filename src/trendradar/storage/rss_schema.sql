
-- RSS 源信息表
CREATE TABLE IF NOT EXISTS rss_feeds (
    id TEXT PRIMARY KEY,
    name TEXT,
    updated_at TEXT
);

-- RSS 条目主表
CREATE TABLE IF NOT EXISTS rss_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    feed_id TEXT,
    url TEXT,
    published_at TEXT,
    summary TEXT,
    author TEXT,
    image_url TEXT DEFAULT '',
    first_crawl_time TEXT,
    last_crawl_time TEXT,
    crawl_count INTEGER DEFAULT 1,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (feed_id) REFERENCES rss_feeds(id)
);

-- RSS 抓取批次记录
CREATE TABLE IF NOT EXISTS rss_crawl_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crawl_time TEXT UNIQUE,
    total_items INTEGER,
    created_at TEXT
);

-- RSS 抓取状态详情
CREATE TABLE IF NOT EXISTS rss_crawl_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crawl_record_id INTEGER,
    feed_id TEXT,
    status TEXT, -- 'success' or 'failed'
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (crawl_record_id) REFERENCES rss_crawl_records(id),
    UNIQUE(crawl_record_id, feed_id)
);
