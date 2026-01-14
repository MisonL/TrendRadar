# coding=utf-8
"""
应用上下文模块

提供配置上下文类，封装所有依赖配置的操作，消除全局状态和包装函数。
"""

from datetime import datetime
import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from trendradar.utils.time import (
    get_configured_time,
    format_date_folder,
    format_time_filename,
    get_current_time_display,
    convert_time_for_display,
)
from trendradar.core import (
    load_frequency_words,
    matches_word_groups,
    save_titles_to_file,
    read_all_today_titles,
    detect_latest_new_titles,
    count_word_frequency,
)
from trendradar.report import (
    clean_title,
    prepare_report_data,
    generate_html_report,
    render_html_content,
)
from trendradar.notification import (
    render_feishu_content,
    render_dingtalk_content,
    split_content_into_batches,
    NotificationDispatcher,
    PushRecordManager,
)
from trendradar.storage import get_storage_manager

logger = logging.getLogger(__name__)


class AppContext:
    """
    应用上下文类

    封装所有依赖配置的操作，提供统一的接口。
    消除对全局 CONFIG 的依赖，提高可测试性。

    使用示例:
        config = load_config()
        ctx = AppContext(config)

        # 时间操作
        now = ctx.get_time()
        date_folder = ctx.format_date()

        # 存储操作
        storage = ctx.get_storage_manager()

        # 报告生成
        html = ctx.generate_html_report(stats, total_titles, ...)
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化应用上下文

        Args:
            config: 完整的配置字典
        """
        self.config = config
        self._storage_manager = None
        self._llm_service = None
        
        # 全局 HTTP 客户端，用于连接池复用
        # 限制并发连接数，防止耗尽资源
        self.http_client = httpx.AsyncClient(
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            }
        )

    async def aclose(self):
        """异步关闭资源"""
        if self.http_client:
            await self.http_client.aclose()

    # === 配置访问 ===

    @property
    def timezone(self) -> str:
        """获取配置的时区"""
        return self.config.get("TIMEZONE", "Asia/Shanghai")

    @property
    def rank_threshold(self) -> int:
        """获取排名阈值"""
        return self.config.get("RANK_THRESHOLD", 50)

    @property
    def weight_config(self) -> Dict:
        """获取权重配置"""
        return self.config.get("WEIGHT_CONFIG", {})

    @property
    def platforms(self) -> List[Dict]:
        """获取平台配置列表"""
        return self.config.get("PLATFORMS", [])

    @property
    def platform_ids(self) -> List[str]:
        """获取平台ID列表"""
        return [p["id"] for p in self.platforms]

    @property
    def rss_config(self) -> Dict:
        """获取 RSS 配置"""
        return self.config.get("RSS", {})

    @property
    def rss_enabled(self) -> bool:
        """RSS 是否启用"""
        return self.rss_config.get("ENABLED", False)

    @property
    def rss_feeds(self) -> List[Dict]:
        """获取 RSS 源列表"""
        return self.rss_config.get("FEEDS", [])

    @property
    def display_mode(self) -> str:
        """获取显示模式 (keyword | platform)"""
        return self.config.get("DISPLAY_MODE", "keyword")

    # === 时间操作 ===

    def get_time(self) -> datetime:
        """获取当前配置时区的时间"""
        return get_configured_time(self.timezone)

    def format_date(self) -> str:
        """格式化日期文件夹 (YYYY-MM-DD)"""
        return format_date_folder(timezone=self.timezone)

    def format_time(self) -> str:
        """格式化时间文件名 (HH-MM)"""
        return format_time_filename(self.timezone)

    def get_time_display(self) -> str:
        """获取时间显示 (HH:MM)"""
        return get_current_time_display(self.timezone)

    @staticmethod
    def convert_time_display(time_str: str) -> str:
        """将 HH-MM 转换为 HH:MM"""
        return convert_time_for_display(time_str)

    # === 存储操作 ===

    def get_storage_manager(self):
        """获取存储管理器（延迟初始化，单例）"""
        if self._storage_manager is None:
            storage_config = self.config.get("STORAGE", {})
            remote_config = storage_config.get("REMOTE", {})
            local_config = storage_config.get("LOCAL", {})
            pull_config = storage_config.get("PULL", {})

            self._storage_manager = get_storage_manager(
                backend_type=storage_config.get("BACKEND", "auto"),
                data_dir=local_config.get("DATA_DIR", "output"),
                enable_txt=storage_config.get("FORMATS", {}).get("TXT", True),
                enable_html=storage_config.get("FORMATS", {}).get("HTML", True),
                remote_config={
                    "bucket_name": remote_config.get("BUCKET_NAME", ""),
                    "access_key_id": remote_config.get("ACCESS_KEY_ID", ""),
                    "secret_access_key": remote_config.get("SECRET_ACCESS_KEY", ""),
                    "endpoint_url": remote_config.get("ENDPOINT_URL", ""),
                    "region": remote_config.get("REGION", ""),
                },
                local_retention_days=local_config.get("RETENTION_DAYS", 0),
                remote_retention_days=remote_config.get("RETENTION_DAYS", 0),
                pull_enabled=pull_config.get("ENABLED", False),
                pull_days=pull_config.get("DAYS", 7),
                timezone=self.timezone,
                http_client=self.http_client,
            )
        return self._storage_manager

    def get_output_path(self, subfolder: str, filename: str) -> str:
        """获取输出路径"""
        output_dir = Path("output") / self.format_date() / subfolder
        output_dir.mkdir(parents=True, exist_ok=True)
        return str(output_dir / filename)

    # === LLM 服务 ===

    def get_llm_service(self):
        """获取 LLM 服务实例（延迟导入）"""
        if self._llm_service is None:
            from trendradar.core.llm_service import LLMService
            self._llm_service = LLMService(self.config)
        return self._llm_service

    # === 数据处理 ===

    def save_titles(self, results: Dict, id_to_name: Dict, failed_ids: List) -> str:
        """保存标题到文件"""
        output_path = self.get_output_path("txt", f"{self.format_time()}.txt")
        return save_titles_to_file(results, id_to_name, failed_ids, output_path, clean_title)

    def read_today_titles(
        self, platform_ids: Optional[List[str]] = None, quiet: bool = False
    ) -> Tuple[Dict, Dict, Dict]:
        """读取当天所有标题"""
        return read_all_today_titles(self.get_storage_manager(), platform_ids, quiet=quiet)

    def detect_new_titles(
        self, platform_ids: Optional[List[str]] = None, quiet: bool = False
    ) -> Dict:
        """检测最新批次的新增标题"""
        return detect_latest_new_titles(self.get_storage_manager(), platform_ids, quiet=quiet)

    def is_first_crawl(self) -> bool:
        """检测是否是当天第一次爬取"""
        return self.get_storage_manager().is_first_crawl_today()

    # === 频率词处理 ===

    def load_frequency_words(
        self, frequency_file: Optional[str] = None
    ) -> Tuple[List[Dict], List[str], List[str]]:
        """加载频率词配置"""
        return load_frequency_words(frequency_file)

    def matches_word_groups(
        self,
        title: str,
        word_groups: List[Dict],
        filter_words: List[str],
        global_filters: Optional[List[str]] = None,
    ) -> bool:
        """检查标题是否匹配词组规则"""
        return matches_word_groups(title, word_groups, filter_words, global_filters)

    # === 统计分析 ===

    def count_frequency(
        self,
        results: Dict,
        word_groups: List[Dict],
        filter_words: List[str],
        id_to_name: Dict,
        title_info: Optional[Dict] = None,
        new_titles: Optional[Dict] = None,
        mode: str = "daily",
        global_filters: Optional[List[str]] = None,
        quiet: bool = False,
    ) -> Tuple[List[Dict], int]:
        """统计词频"""
        return count_word_frequency(
            results=results,
            word_groups=word_groups,
            filter_words=filter_words,
            id_to_name=id_to_name,
            title_info=title_info,
            rank_threshold=self.rank_threshold,
            new_titles=new_titles,
            mode=mode,
            global_filters=global_filters,
            weight_config=self.weight_config,
            max_news_per_keyword=self.config.get("MAX_NEWS_PER_KEYWORD", 0),
            sort_by_position_first=self.config.get("SORT_BY_POSITION_FIRST", False),
            is_first_crawl_func=self.is_first_crawl,
            convert_time_func=self.convert_time_display,
            quiet=quiet,
        )

    # === 报告生成 ===

    def prepare_report(
        self,
        stats: List[Dict],
        failed_ids: Optional[List] = None,
        new_titles: Optional[Dict] = None,
        id_to_name: Optional[Dict] = None,
        mode: str = "daily",
    ) -> Dict:
        """准备报告数据"""
        data = prepare_report_data(
            stats=stats,
            failed_ids=failed_ids,
            new_titles=new_titles,
            id_to_name=id_to_name,
            mode=mode,
            rank_threshold=self.rank_threshold,
            matches_word_groups_func=self.matches_word_groups,
            load_frequency_words_func=self.load_frequency_words,
        )
        data["report_title"] = self.config.get("REPORT_TITLE", "热点新闻分析")
        
        # 尝试丰富图片链接 (将原始链接转换为本地缓存的 Web 链接)
        self.enrich_with_display_images(data)
        
        return data

    def generate_html(
        self,
        stats: List[Dict],
        total_titles: int,
        failed_ids: Optional[List] = None,
        new_titles: Optional[Dict] = None,
        id_to_name: Optional[Dict] = None,
        mode: str = "daily",
        is_daily_summary: bool = False,
        update_info: Optional[Dict] = None,
        rss_items: Optional[List[Dict]] = None,
        rss_new_items: Optional[List[Dict]] = None,
    ) -> str:
        """生成HTML报告"""
        return generate_html_report(
            stats=stats,
            total_titles=total_titles,
            failed_ids=failed_ids,
            new_titles=new_titles,
            id_to_name=id_to_name,
            mode=mode,
            is_daily_summary=is_daily_summary,
            update_info=update_info,
            rank_threshold=self.rank_threshold,
            output_dir="output",
            date_folder=self.format_date(),
            time_filename=self.format_time(),
            render_html_func=lambda *args, **kwargs: self.render_html(*args, rss_items=rss_items, rss_new_items=rss_new_items, **kwargs),
            matches_word_groups_func=self.matches_word_groups,
            load_frequency_words_func=self.load_frequency_words,
            enable_index_copy=True,
        )

    def render_html(
        self,
        report_data: Dict,
        total_titles: int,
        is_daily_summary: bool = False,
        mode: str = "daily",
        update_info: Optional[Dict] = None,
        rss_items: Optional[List[Dict]] = None,
        rss_new_items: Optional[List[Dict]] = None,
    ) -> str:
        """渲染HTML内容"""
        return render_html_content(
            report_data=report_data,
            total_titles=total_titles,
            is_daily_summary=is_daily_summary,
            mode=mode,
            update_info=update_info,
            reverse_content_order=self.config.get("REVERSE_CONTENT_ORDER", False),
            get_time_func=self.get_time,
            rss_items=rss_items,
            rss_new_items=rss_new_items,
            display_mode=self.display_mode,
            report_title=self.config.get("REPORT_TITLE", "热点新闻分析"),
        )

    def enrich_with_display_images(self, report_data: Dict) -> None:
        """
        丰富图片链接：检查是否存在本地缓存图片，如果有则生成 Web 访问链接覆盖 image_url
        并将原始链接保存在 original_image_url
        """
        web_url = self.config.get("app", {}).get("web_url") or self.config.get("WEB_URL")
        if not web_url:
            return

        # 确保 web_url 不包含结尾斜杠，并且 /images 路径正确映射
        # 假设 web_url 是 http://server:port，图片路由是 /images
        # ImageCache.get_cached_url 会处理 base_url 拼接
        
        image_base_url = f"{web_url.rstrip('/')}/images"
        
        # 1. 处理 stats
        if "stats" in report_data:
            for stat in report_data["stats"]:
                for title_obj in stat["titles"]:
                    # 兼容对象和字典
                    if isinstance(title_obj, dict):
                        img_url = title_obj.get("image_url")
                        if img_url:
                            # 尝试获取缓存链接 (同步检查文件是否存在，不触发下载)
                            # 注意：这里需要 storage_manager 提供同步方法或预先处理
                            # 由于 ImageCache.get_cached_url 是 async 的，这里只能做简单的路径推断
                            # 或者我们假设如果开启了 crawl 且有 cache，文件应该在
                            
                            # 获取 cache 实例
                            # 这里存在一个问题：get_cached_url 是 async 的，而 prepare_report 是 sync 的
                            # 我们需要一个同步的 "get_existing_cache_url" 方法
                            
                            cache = self.get_storage_manager().image_cache
                            if cache:
                                cached_path = cache.find_existing_cache(img_url)
                                if cached_path:
                                    # 转换为 web url
                                    # output/cache/images/yyyy-mm-dd/hash.jpg -> /images/yyyy-mm-dd/hash.jpg
                                    try:
                                        rel_path = cached_path.relative_to(cache.base_dir)
                                        # 统一正斜杠
                                        rel_path_str = str(rel_path).replace("\\", "/")
                                        display_url = f"{image_base_url}/{rel_path_str}"
                                        
                                        title_obj["original_image_url"] = img_url
                                        title_obj["display_image_url"] = display_url
                                    except ValueError:
                                        pass
                                        
        # 2. 处理 new_titles (新增列表)
        if "new_titles" in report_data and isinstance(report_data["new_titles"], dict):
            cache = self.get_storage_manager().image_cache
            if cache:
                for source_id, titles_data in report_data["new_titles"].items():
                    if not isinstance(titles_data, dict):
                        continue
                    for t, info in titles_data.items():
                        if not isinstance(info, dict):
                            continue
                        img_url = info.get("image_url")
                        if img_url:
                            cached_path = cache.find_existing_cache(img_url)
                            if cached_path:
                                try:
                                    rel_path = cached_path.relative_to(cache.base_dir)
                                    rel_path_str = str(rel_path).replace("\\", "/")
                                    info["original_image_url"] = img_url
                                    info["display_image_url"] = f"{image_base_url}/{rel_path_str}"
                                except ValueError:
                                    pass

    # === 通知内容渲染 ===

    def render_feishu(
        self,
        report_data: Dict,
        update_info: Optional[Dict] = None,
        mode: str = "daily",
    ) -> str:
        """渲染飞书内容"""
        return render_feishu_content(
            report_data=report_data,
            update_info=update_info,
            mode=mode,
            separator=self.config.get("FEISHU_MESSAGE_SEPARATOR", "---"),
            reverse_content_order=self.config.get("REVERSE_CONTENT_ORDER", False),
            get_time_func=self.get_time,
        )

    def render_dingtalk(
        self,
        report_data: Dict,
        update_info: Optional[Dict] = None,
        mode: str = "daily",
    ) -> str:
        """渲染钉钉内容"""
        return render_dingtalk_content(
            report_data=report_data,
            update_info=update_info,
            mode=mode,
            reverse_content_order=self.config.get("REVERSE_CONTENT_ORDER", False),
            get_time_func=self.get_time,
        )

    def split_content(
        self,
        report_data: Dict,
        format_type: str,
        update_info: Optional[Dict] = None,
        max_bytes: Optional[int] = None,
        mode: str = "daily",
        rss_items: Optional[list] = None,
        rss_new_items: Optional[list] = None,
    ) -> List[str]:
        """分批处理消息内容（支持热榜+RSS合并）

        Args:
            report_data: 报告数据
            format_type: 格式类型
            update_info: 更新信息
            max_bytes: 最大字节数
            mode: 报告模式
            rss_items: RSS 统计条目列表
            rss_new_items: RSS 新增条目列表

        Returns:
            分批后的消息内容列表
        """
        return split_content_into_batches(
            report_data=report_data,
            format_type=format_type,
            update_info=update_info,
            max_bytes=max_bytes,
            mode=mode,
            batch_sizes={
                "dingtalk": self.config.get("DINGTALK_BATCH_SIZE", 20000),
                "feishu": self.config.get("FEISHU_BATCH_SIZE", 29000),
                "default": self.config.get("MESSAGE_BATCH_SIZE", 4000),
            },
            feishu_separator=self.config.get("FEISHU_MESSAGE_SEPARATOR", "---"),
            reverse_content_order=self.config.get("REVERSE_CONTENT_ORDER", False),
            get_time_func=self.get_time,
            rss_items=rss_items,
            rss_new_items=rss_new_items,
            timezone=self.config.get("TIMEZONE", "Asia/Shanghai"),
            display_mode=self.display_mode,
            max_notify_news=self.config.get("MAX_NOTIFY_NEWS", 5),
            web_url=self.config.get("WEB_URL", ""),
        )

    # === 通知发送 ===

    def create_notification_dispatcher(self) -> NotificationDispatcher:
        """创建通知调度器"""
        return NotificationDispatcher(
            config=self.config,
            get_time_func=self.get_time,
            split_content_func=self.split_content,
        )

    def create_push_manager(self) -> PushRecordManager:
        """创建推送记录管理器"""
        return PushRecordManager(
            storage_backend=self.get_storage_manager(),
            get_time_func=self.get_time,
        )

    # === 消息去重 ===

    def get_content_hash(self, item_url: str, item_title: str, item_source: str) -> str:
        """计算内容哈希值"""
        dedup_config = self.config.get("NOTIFICATION", {}).get("deduplication", {})
        use_url_hash = dedup_config.get("use_url_hash", True)

        if use_url_hash and item_url:
            # 使用 URL 哈希
            return hashlib.md5(item_url.encode("utf-8")).hexdigest()
        else:
            # 使用 标题+来源 哈希
            content = f"{item_source}:{item_title}"
            return hashlib.md5(content.encode("utf-8")).hexdigest()

    def deduplicate_report_data(
        self, report_data: Dict
    ) -> Tuple[Dict, List[Dict]]:
        """
        对报告数据进行去重处理

        优化：使用批量查询接口一次性查询所有 hash，减少数据库往返次数

        Args:
            report_data: 原始报告数据

        Returns:
            (filtered_report_data, items_to_record)
            - filtered_report_data: 去重后的报告数据（可直接用于发送）
            - items_to_record: 需要记录到已推送表的数据列表
        """
        dedup_config = self.config.get("NOTIFICATION", {}).get("deduplication", {})
        if not dedup_config.get("enabled", False):
            return report_data, []

        items_to_record = []
        filtered_stats = []

        # 第一步：收集所有需要查询的 hash（热榜数据）
        hash_to_info = {}  # {hash: {title, url, source_id, title_obj}}
        
        if "stats" in report_data:
            for stat in report_data["stats"]:
                for title_obj in stat["titles"]:
                    # title_obj 可能是 NewsItem 对象或字典，需兼容处理
                    if hasattr(title_obj, "url"):
                        url = title_obj.url
                        title = title_obj.title
                        source_id = title_obj.source_id
                    else:
                        url = title_obj.get("url", "")
                        title = title_obj.get("title", "")
                        source_id = title_obj.get("source_id", "")

                    content_hash = self.get_content_hash(url, title, source_id)
                    hash_to_info[content_hash] = {
                        "title": title,
                        "url": url,
                        "source_id": source_id,
                        "title_obj": title_obj,
                        "stat": stat
                    }
        
        # 第二步：批量查询所有 hash 是否已推送
        pushed_hashes = set()
        if hash_to_info:
            batch_result = self.get_storage_manager().is_news_pushed_batch(list(hash_to_info.keys()))
            pushed_hashes = {h for h, is_pushed in batch_result.items() if is_pushed}
        
        # 第三步：过滤未推送的新闻
        for content_hash, info in hash_to_info.items():
            if content_hash not in pushed_hashes:
                # 未推送，添加到结果
                title_obj = info["title_obj"]
                
                # 找到对应的 stat 并添加标题
                stat = info["stat"]
                if stat not in filtered_stats:
                    new_stat = stat.copy()
                    new_stat["titles"] = []
                    new_stat["count"] = 0
                    filtered_stats.append(new_stat)
                
                # 找到对应的 filtered_stat
                for filtered_stat in filtered_stats:
                    if filtered_stat["word"] == stat["word"]:
                        filtered_stat["titles"].append(title_obj)
                        filtered_stat["count"] += 1
                        break
                
                # 添加到记录列表
                items_to_record.append({
                    "hash": content_hash,
                    "title": info["title"],
                    "url": info["url"]
                })
            else:
                logger.info(f"[去重] 过滤已推送新闻: {info['title'][:20]}...")

        # 构建新的 report_data
        filtered_data = report_data.copy()
        if "stats" in report_data:
            filtered_data["stats"] = filtered_stats
            
        # 处理 new_titles (新增列表)
        if dedup_config.get("dedup_new_titles", True) and "new_titles" in report_data:
            # handle list structure (from prepare_report_data)
            if isinstance(report_data["new_titles"], list):
                new_titles_list = report_data["new_titles"]
                
                # 1. Collect all hashes
                all_hashes = []
                # hash -> {title, url} for recording lookup is implicit in loop below if we iterate twice
                # checking is simpler if we just process source by source?
                # No, batch query is better.
                

                
                for source_item in new_titles_list:
                    source_id = source_item.get("source_id", "")
                    for title_data in source_item.get("titles", []):
                        title = title_data.get("title", "")
                        url = title_data.get("url", "")
                        h = self.get_content_hash(url, title, source_id)
                        all_hashes.append(h)
                
                # 2. Batch query
                pushed_hashes = set()
                if all_hashes:
                    # remove duplicates in query list
                    unique_hashes = list(set(all_hashes))
                    batch_result = self.get_storage_manager().is_news_pushed_batch(unique_hashes)
                    pushed_hashes = {h for h, is_pushed in batch_result.items() if is_pushed}
                
                # 3. Filter and rebuild list
                filtered_new_titles_list = []
                
                for source_item in new_titles_list:
                    source_id = source_item.get("source_id", "")
                    filtered_titles = []
                    
                    for title_data in source_item.get("titles", []):
                        title = title_data.get("title", "")
                        url = title_data.get("url", "")
                        h = self.get_content_hash(url, title, source_id)
                        
                        if h not in pushed_hashes:
                            filtered_titles.append(title_data)
                            items_to_record.append({
                                "hash": h,
                                "title": title,
                                "url": url
                            })
                    
                    if filtered_titles:
                        new_source_item = source_item.copy()
                        new_source_item["titles"] = filtered_titles
                        filtered_new_titles_list.append(new_source_item)
                
                filtered_data["new_titles"] = filtered_new_titles_list
            
            # Fallback for legacy dict structure
            elif isinstance(report_data["new_titles"], dict):
                # 收集 new_titles 的 hash
                new_titles_hash_to_info = {}
                
                for source_id, titles_dict in report_data["new_titles"].items():
                    for title_text, title_info in titles_dict.items():
                        url = title_info.get("url", "")
                        content_hash = self.get_content_hash(url, title_text, source_id)
                        new_titles_hash_to_info[content_hash] = {
                            "title": title_text,
                            "url": url,
                            "source_id": source_id,
                            "title_info": title_info
                        }
                
                # 批量查询
                new_titles_pushed_hashes = set()
                if new_titles_hash_to_info:
                    batch_result = self.get_storage_manager().is_news_pushed_batch(list(new_titles_hash_to_info.keys()))
                    new_titles_pushed_hashes = {h for h, is_pushed in batch_result.items() if is_pushed}
                
                # 过滤
                filtered_new_titles = {}
                for content_hash, info in new_titles_hash_to_info.items():
                    if content_hash not in new_titles_pushed_hashes:
                        source_id = info["source_id"]
                        if source_id not in filtered_new_titles:
                            filtered_new_titles[source_id] = {}
                        filtered_new_titles[source_id][info["title"]] = info["title_info"]
                        items_to_record.append({
                            "hash": content_hash,
                            "title": info["title"],
                            "url": info["url"]
                        })
                
                filtered_data["new_titles"] = filtered_new_titles
        
        # 记录日志
        original_count = sum(len(s["titles"]) for s in report_data.get("stats", []))
        filtered_count = sum(len(s["titles"]) for s in filtered_stats)
        if original_count != filtered_count:
             logger.info(f"[去重] 过滤前: {original_count} 条, 过滤后: {filtered_count} 条")

        return filtered_data, items_to_record

    def record_pushed_items(self, items: List[Dict]) -> None:
        """批量记录已推送条目"""
        # dedup_config = self.config.get("NOTIFICATION", {}).get("deduplication", {})
        # if not dedup_config.get("enabled", False):
        #    return

        manager = self.get_storage_manager()
        count = 0
        for item in items:
            if manager.record_pushed_news(item["hash"], item["title"], item["url"]):
                count += 1
        
        if count > 0:
            logger.info(f"[去重] 已记录 {count} 条推送历史")

    def deduplicate_rss_data(
        self, rss_items: List[Dict]
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        对 RSS 条目进行去重处理

        优化：使用批量查询接口一次性查询所有 hash，减少数据库往返次数

        Args:
            rss_items: 原始 RSS 条目列表

        Returns:
            (filtered_rss_items, items_to_record)
        """
        dedup_config = self.config.get("NOTIFICATION", {}).get("deduplication", {})
        if not dedup_config.get("enabled", False) or not rss_items:
            return rss_items, []

        # 第一步：收集所有需要查询的 hash
        hash_to_info = {}  # {hash: {title, url, feed_id, item}}
        
        for item in rss_items:
            url = item.get("url", "")
            title = item.get("title", "")
            feed_id = item.get("feed_id", "")
            
            content_hash = self.get_content_hash(url, title, feed_id)
            hash_to_info[content_hash] = {
                "title": title,
                "url": url,
                "feed_id": feed_id,
                "item": item
            }
        
        # 第二步：批量查询所有 hash 是否已推送
        pushed_hashes = set()
        if hash_to_info:
            batch_result = self.get_storage_manager().is_news_pushed_batch(list(hash_to_info.keys()))
            pushed_hashes = {h for h, is_pushed in batch_result.items() if is_pushed}
        
        # 第三步：过滤未推送的 RSS 条目
        filtered_items = []
        items_to_record = []
        
        for content_hash, info in hash_to_info.items():
            if content_hash not in pushed_hashes:
                # 未推送，添加到结果
                filtered_items.append(info["item"])
                items_to_record.append({
                    "hash": content_hash,
                    "title": info["title"],
                    "url": info["url"]
                })
            else:
                # print(f"[去重] 过滤已推送 RSS: {info['title'][:20]}...")
                pass

        if len(rss_items) != len(filtered_items):
            print(f"[去重] RSS 过滤前: {len(rss_items)} 条, 过滤后: {len(filtered_items)} 条")

        return filtered_items, items_to_record

    # === 资源清理 ===

    def cleanup(self):
        """清理资源"""
        if self._storage_manager:
            self._storage_manager.cleanup_old_data()
            self._storage_manager.cleanup()
            self._storage_manager = None
