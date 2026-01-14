
import sqlite3
from trendradar.storage.local import LocalStorageBackend
from trendradar.storage.base import NewsItem, NewsData

def test_storage_migration(tmp_path):
    # Create a legacy DB without image_url in the location LocalStorageBackend expects
    db_dir = tmp_path / "news"
    db_dir.mkdir(parents=True)
    db_path = db_dir / "2026-01-13.db"
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE news_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT,
            title TEXT,
            url TEXT,
            first_crawl_time TEXT,
            last_crawl_time TEXT,
            crawl_count INTEGER
        )
    """)
    conn.commit()
    conn.close()

    # Initialize backend and trigger migration
    backend = LocalStorageBackend(data_dir=str(tmp_path))
    
    # Save some data to trigger _init_tables and migration
    item = NewsItem(title="Test", source_id="test", rank=1, url="http://test.com", crawl_time="12:00")
    data = NewsData(date="2026-01-13", crawl_time="12:00", items={"test": [item]})
    backend.save_news_data(data)

    # Verify column exists now
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(news_items)")
    columns = [row[1] for row in cursor.fetchall()]
    conn.close()
    
    assert "image_url" in columns
