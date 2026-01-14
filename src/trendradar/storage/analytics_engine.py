
import os
import duckdb
import logging
import asyncio
from typing import List, Dict
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

class AnalyticsEngine:
    """
    DuckDB 分析引擎
    
    负责处理跨天、跨平台的大规模数据聚合分析。
    使用 DuckDB 的 OLAP 能力加速查询。
    """
    
    def __init__(self, data_dir: str = "output", db_path: str = "output/analytics.duckdb"):
        self.data_dir = data_dir
        self.db_path = db_path
        self._conn = None
        self._sqlite_loaded = False
        
    def connect(self):
        """连接到 DuckDB 实例"""
        if self._conn is None:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self._conn = duckdb.connect(self.db_path)
            self._init_schema()
        return self._conn
        
    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def _init_schema(self):
        """初始化数据模型"""
        # 创建统一的新闻宽表
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS news_archive (
                title VARCHAR,
                url VARCHAR,
                platform VARCHAR,
                publish_time VARCHAR,
                fetch_time VARCHAR,
                rank INTEGER,
                hot_value DOUBLE,
                keywords VARCHAR[],
                partition_date DATE
            )
        """)
        
        # 创建索引
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_news_time ON news_archive(fetch_time)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_news_platform ON news_archive(platform)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_news_partition ON news_archive(partition_date)")

        self._create_views()

    def _create_views(self):
        """创建预计算视图"""
        # 每日热点视图
        self._conn.execute("""
            CREATE OR REPLACE VIEW daily_trends AS
            SELECT 
                title, 
                ANY_VALUE(url) as url,
                ANY_VALUE(platform) as platform,
                MIN(fetch_time) as first_seen,
                MAX(fetch_time) as last_seen,
                MIN(rank) as best_rank, -- rank 1 is best
                COUNT(*) as occurrences,
                partition_date
            FROM news_archive
            GROUP BY title, partition_date
        """)
        
        # 平台分布视图
        self._conn.execute("""
            CREATE OR REPLACE VIEW platform_stats AS
            SELECT 
                platform, 
                COUNT(DISTINCT title) as news_count,
                AVG(rank) as avg_rank,
                partition_date
            FROM news_archive
            GROUP BY platform, partition_date
        """)
        
    def sync_data(self, days: int = 7):
        """
        从 SQLite 归档同步数据到 DuckDB (增量)
        """
        """
        从 SQLite 归档同步数据到 DuckDB (增量)
        
        注意：此方法会在内部创建新的连接以确保线程安全，
        适合在 asyncio.to_thread 中运行。
        """
        # 使用本地连接，不使用 self.connect()，确保线程安全
        try:
            conn = duckdb.connect(self.db_path)
            # 初始化 schema (为了确保表存在)
            # 注意：重复建表 IF NOT EXISTS 是安全的
            conn.execute("""
                CREATE TABLE IF NOT EXISTS news_archive (
                    title VARCHAR,
                    url VARCHAR,
                    platform VARCHAR,
                    publish_time VARCHAR,
                    fetch_time VARCHAR,
                    rank INTEGER,
                    hot_value DOUBLE,
                    keywords VARCHAR[],
                    partition_date DATE
                )
            """)
            
            # 加载 SQLite 扩展
            conn.execute("INSTALL sqlite; LOAD sqlite;")
        except Exception as e:
            logger.error(f"[DuckDB] 初始化同步连接失败: {e}")
            return

        data_path = Path(self.data_dir)
        today = datetime.now()
        
        # 为了保证日期界限正确，如果是凌晨运行，可能需要多追溯一天
        for i in range(days + 1):
            current_day = today - timedelta(days=i)
            date_str = current_day.strftime("%Y-%m-%d")
            sqlite_path = data_path / date_str / "news.db"
            
            if not sqlite_path.exists():
                continue
                
            try:
                # 附加 SQLite 数据库
                db_alias = f"sqlite_src_{i}"
                conn.execute(f"ATTACH '{str(sqlite_path)}' AS {db_alias} (TYPE SQLITE)")
                
                # 同步数据
                query = f"""
                    INSERT INTO news_archive 
                    SELECT 
                        n.title, 
                        n.url, 
                        n.platform_id as platform,
                        n.first_crawl_time as publish_time, 
                        rh.crawl_time as fetch_time, 
                        rh.rank, 
                        0.0 as hot_value, 
                        [] as keywords,
                        '{date_str}'::DATE as partition_date
                    FROM {db_alias}.rank_history rh
                    JOIN {db_alias}.news_items n ON rh.news_item_id = n.id
                    WHERE NOT EXISTS (
                        SELECT 1 FROM news_archive na 
                        WHERE na.title = n.title 
                        AND na.platform = n.platform_id 
                        AND na.fetch_time = rh.crawl_time
                    )
                """
                conn.execute(query)
                conn.execute(f"DETACH {db_alias}")
                logger.info(f"[DuckDB] 已同步日期数据: {date_str}")
                
            except Exception as e:
                logger.error(f"[DuckDB] 同步日期 {date_str} 失败: {e}")
                try:
                    conn.execute(f"DETACH {db_alias}")
                except Exception:
                    pass
        
        # 关闭本地连接
        try:
            conn.close()
        except Exception:
            pass

    async def sync_data_async(self, days: int = 7):
        """异步执行数据同步（防止阻塞事件循环）"""
        return await asyncio.to_thread(self.sync_data, days)

    def get_trending_keywords(self, days: int = 7, limit: int = 20) -> List[Dict]:
        """获取热词趋势 (待进一步实现)"""
        return []
