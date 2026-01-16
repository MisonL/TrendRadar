# coding=utf-8
"""
TrendRadar 主程序

热点新闻聚合与分析工具
支持: python -m trendradar
"""

import os
import webbrowser
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import asyncio
import requests
import logging

from trendradar.context import AppContext
from trendradar import __version__
from trendradar.core import load_config
from trendradar.core.analyzer import convert_keyword_stats_to_platform_stats
from trendradar.crawler import AsyncDataFetcher
from trendradar.storage import convert_crawl_results_to_news_data
from trendradar.utils.time import is_within_days
from trendradar.notification.coordinator import NotificationCoordinator


def check_version_update(
    current_version: str, version_url: str, proxy_url: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """检查版本更新"""
    try:
        proxies = None
        if proxy_url:
            proxies = {"http": proxy_url, "https": proxy_url}

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/plain, */*",
            "Cache-Control": "no-cache",
        }

        response = requests.get(
            version_url, proxies=proxies, headers=headers, timeout=10
        )
        response.raise_for_status()

        remote_version = response.text.strip()
        logging.getLogger("TrendRadar").info(f"当前版本: {current_version}, 远程版本: {remote_version}")

        # 比较版本
        def parse_version(version_str):
            try:
                parts = version_str.strip().split(".")
                if len(parts) != 3:
                    raise ValueError("版本号格式不正确")
                return int(parts[0]), int(parts[1]), int(parts[2])
            except Exception:
                return 0, 0, 0

        current_tuple = parse_version(current_version)
        remote_tuple = parse_version(remote_version)

        need_update = current_tuple < remote_tuple
        return need_update, remote_version if need_update else None

    except Exception as e:
        # 这里因为是静态函数且 logger 还没初始化好，暂时保持简单打印或使用 root logger
        logging.getLogger("TrendRadar").warning(f"版本检查失败: {e}")
        return False, None


# === 主分析器 ===
class NewsAnalyzer:
    """新闻分析器"""

    # 模式策略定义
    MODE_STRATEGIES = {
        "incremental": {
            "mode_name": "增量模式",
            "description": "增量模式（只关注新增新闻，无新增时不推送）",
            "realtime_report_type": "实时增量",
            "summary_report_type": "当日汇总",
            "should_send_realtime": True,
            "should_generate_summary": True,
            "summary_mode": "daily",
        },
        "current": {
            "mode_name": "当前榜单模式",
            "description": "当前榜单模式（当前榜单匹配新闻 + 新增新闻区域 + 按时推送）",
            "realtime_report_type": "实时当前榜单",
            "summary_report_type": "当前榜单汇总",
            "should_send_realtime": True,
            "should_generate_summary": True,
            "summary_mode": "current",
        },
        "daily": {
            "mode_name": "当日汇总模式",
            "description": "当日汇总模式（所有匹配新闻 + 新增新闻区域 + 按时推送）",
            "realtime_report_type": "",
            "summary_report_type": "当日汇总",
            "should_send_realtime": False,
            "should_generate_summary": True,
            "summary_mode": "daily",
        },
    }

    def __init__(self):
        # 配置日志
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        self.logger = logging.getLogger("TrendRadar")

        # 加载配置
        self.logger.info("正在加载配置...")
        config = load_config()
        self.logger.info(f"TrendRadar v{__version__} 配置加载完成")
        self.logger.info(f"监控平台数量: {len(config['PLATFORMS'])}")
        self.logger.info(f"时区: {config.get('TIMEZONE', 'Asia/Shanghai')}")

        # 创建应用上下文
        self.ctx = AppContext(config)

        self.request_interval = self.ctx.config["REQUEST_INTERVAL"]
        self.report_mode = self.ctx.config["REPORT_MODE"]
        self.rank_threshold = self.ctx.rank_threshold
        self.is_github_actions = os.environ.get("GITHUB_ACTIONS") == "true"
        self.is_docker_container = self._detect_docker_environment()
        self.update_info = None
        self.proxy_url = None
        self._setup_proxy()
        self.data_fetcher = AsyncDataFetcher(
            self.proxy_url, 
            max_concurrency=10, 
            client=self.ctx.http_client
        )

        # 初始化存储管理器（使用 AppContext）
        self._init_storage_manager()

        # 初始化 NotificationDispatcher 和 PushManager
        self.notification_dispatcher = self.ctx.create_notification_dispatcher()
        self.push_manager = self.ctx.create_push_manager()

        # 初始化通知协调器
        self.notification_coordinator = NotificationCoordinator(
            config=self.ctx.config,
            storage_manager=self.storage_manager,
            notification_dispatcher=self.notification_dispatcher,
            push_manager=self.push_manager,
            ctx=self.ctx
        )

        # 注册退出清理
        import atexit
        atexit.register(self.storage_manager.cleanup)

        if self.is_github_actions:
            self._check_version_update()

    def _init_storage_manager(self) -> None:
        """初始化存储管理器（使用 AppContext）"""
        # 获取数据保留天数（支持环境变量覆盖）
        env_retention = os.environ.get("STORAGE_RETENTION_DAYS", "").strip()
        if env_retention:
            # 环境变量覆盖配置
            self.ctx.config["STORAGE"]["RETENTION_DAYS"] = int(env_retention)

        self.storage_manager = self.ctx.get_storage_manager()
        self.logger.info(f"存储后端: {self.storage_manager.backend_name}")

        retention_days = self.ctx.config.get("STORAGE", {}).get("RETENTION_DAYS", 0)
        if retention_days > 0:
            self.logger.info(f"数据保留天数: {retention_days} 天")

    async def _cache_urls(self, urls: List[str]) -> None:
        """批量缓存图片 URL (异步)"""
        if not urls:
            return

        try:
            # 简单去重
            unique_urls = list(set([u for u in urls if u and u.strip()]))
            if not unique_urls:
                return

            self.logger.info(f"[图片缓存] 开始处理 {len(unique_urls)} 张图片...")
            image_cache = self.storage_manager.get_image_cache()

            tasks = []
            for url in unique_urls:
                tasks.append(image_cache.download(url))
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
            self.logger.error(f"[图片缓存] 异常: {e}")

    def _detect_docker_environment(self) -> bool:
        """检测是否运行在 Docker 容器中"""
        try:
            if os.environ.get("DOCKER_CONTAINER") == "true":
                return True

            if os.path.exists("/.dockerenv"):
                return True

            return False
        except Exception:
            return False

    def _should_open_browser(self) -> bool:
        """判断是否应该打开浏览器"""
        return not self.is_github_actions and not self.is_docker_container

    def _setup_proxy(self) -> None:
        """设置代理配置"""
        if not self.is_github_actions and self.ctx.config["USE_PROXY"]:
            self.proxy_url = self.ctx.config["DEFAULT_PROXY"]
            self.logger.info("本地环境，使用代理")
        elif not self.is_github_actions and not self.ctx.config["USE_PROXY"]:
            self.logger.info("本地环境，未启用代理")
        else:
            self.logger.info("GitHub Actions环境，不使用代理")

    def _check_version_update(self) -> None:
        """检查版本更新"""
        try:
            need_update, remote_version = check_version_update(
                __version__, self.ctx.config["VERSION_CHECK_URL"], self.proxy_url
            )

            if need_update and remote_version:
                self.update_info = {
                    "current_version": __version__,
                    "remote_version": remote_version,
                }
                self.logger.info(f"发现新版本: {remote_version} (当前: {__version__})")
            else:
                self.logger.info("版本检查完成，当前为最新版本")
        except Exception as e:
            self.logger.warning(f"版本检查出错: {e}")

    def _get_mode_strategy(self) -> Dict:
        """获取当前模式的策略配置"""
        return self.MODE_STRATEGIES.get(self.report_mode, self.MODE_STRATEGIES["daily"])

    def _load_analysis_data(
        self,
        quiet: bool = False,
    ) -> Optional[Tuple[Dict, Dict, Dict, Dict, List, List]]:
        """统一的数据加载和预处理，使用当前监控平台列表过滤历史数据"""
        try:
            # 获取当前配置的监控平台ID列表
            current_platform_ids = self.ctx.platform_ids
            if not quiet:
                self.logger.info(f"当前监控平台: {current_platform_ids}")

            all_results, id_to_name, title_info = self.ctx.read_today_titles(
                current_platform_ids, quiet=quiet
            )

            if not all_results:
                self.logger.info("没有找到当天的数据")
                return None

            total_titles = sum(len(titles) for titles in all_results.values())
            if not quiet:
                self.logger.info(f"读取到 {total_titles} 个标题（已按当前监控平台过滤）")

            new_titles = self.ctx.detect_new_titles(current_platform_ids, quiet=quiet)
            word_groups, filter_words, global_filters = self.ctx.load_frequency_words()

            return (
                all_results,
                id_to_name,
                title_info,
                new_titles,
                word_groups,
                filter_words,
                global_filters,
            )
        except Exception as e:
            self.logger.error(f"数据加载失败: {e}")
            return None

    def _prepare_current_title_info(self, results: Dict, time_info: str) -> Dict:
        """从当前抓取结果构建标题信息"""
        title_info = {}
        for source_id, titles_data in results.items():
            title_info[source_id] = {}
            for title, title_data in titles_data.items():
                ranks = title_data.get("ranks", [])
                url = title_data.get("url", "")
                mobile_url = title_data.get("mobileUrl", "")

                title_info[source_id][title] = {
                    "first_time": time_info,
                    "last_time": time_info,
                    "count": 1,
                    "ranks": ranks,
                    "url": url,
                    "mobileUrl": mobile_url,
                }
        return title_info

    async def _run_analysis_pipeline(
        self,
        data_source: Dict,
        mode: str,
        title_info: Dict,
        new_titles: Dict,
        word_groups: List[Dict],
        filter_words: List[str],
        id_to_name: Dict,
        failed_ids: Optional[List] = None,
        is_daily_summary: bool = False,
        global_filters: Optional[List[str]] = None,
        quiet: bool = False,
        rss_items: Optional[List[Dict]] = None,
        rss_new_items: Optional[List[Dict]] = None,
    ) -> Tuple[List[Dict], Optional[str]]:
        """统一的分析流水线：数据处理 → 统计计算 → HTML生成"""

        # 统计计算（使用 AppContext）
        stats, total_titles = self.ctx.count_frequency(
            data_source,
            word_groups,
            filter_words,
            id_to_name,
            title_info,
            new_titles,
            mode=mode,
            global_filters=global_filters,
            quiet=quiet,
        )

        # === LLM 智能评分与过滤 ===
        llm = self.ctx.get_llm_service()
        if llm.enabled and stats:
            if not quiet:
                self.logger.info(f"[LLM] 开始智能分析 (模型: {llm.model})...")
            
            # 1. 收集所有需要评分的标题
            all_titles = set()
            for stat in stats:
                for title_data in stat["titles"]:
                    all_titles.add(title_data["title"])
            
            # 2. 批量评分
            if all_titles:
                scores = await llm.score_titles(list(all_titles))
                threshold = llm.config.get("score_threshold", 6.0)
                
                # 3. 过滤低分文章
                filtered_stats = []
                filtered_count = 0
                
                for stat in stats:
                    new_group_titles = []
                    for title_data in stat["titles"]:
                        title = title_data["title"]
                        score = scores.get(title, 0.0)
                        title_data["llm_score"] = score
                        
                        if score >= threshold:
                            new_group_titles.append(title_data)
                        else:
                            filtered_count += 1
                    
                    if new_group_titles:
                        stat["titles"] = new_group_titles
                        stat["count"] = len(new_group_titles)
                        filtered_stats.append(stat)
                
                stats = filtered_stats
                if not quiet:
                    self.logger.info(f"[LLM] 分析完成，过滤掉 {filtered_count} 条低质量内容 (阈值: {threshold})")

        # 如果是 platform 模式，转换数据结构
        if self.ctx.display_mode == "platform" and stats:
            stats = convert_keyword_stats_to_platform_stats(
                stats,
                self.ctx.weight_config,
                self.ctx.rank_threshold,
            )

        # HTML生成（如果启用）
        html_file = None
        if self.ctx.config["STORAGE"]["FORMATS"]["HTML"]:
            html_file = self.ctx.generate_html(
                stats,
                total_titles,
                failed_ids=failed_ids,
                new_titles=new_titles,
                id_to_name=id_to_name,
                mode=mode,
                is_daily_summary=is_daily_summary,
                update_info=self.update_info if self.ctx.config["SHOW_VERSION_UPDATE"] else None,
                rss_items=rss_items,
                rss_new_items=rss_new_items,
            )

        return stats, html_file

    async def _generate_summary_report(
        self,
        mode_strategy: Dict,
        rss_items: Optional[List[Dict]] = None,
        rss_new_items: Optional[List[Dict]] = None,
        rss_raw_items: Optional[List[Dict]] = None,
    ) -> Optional[str]:
        """生成汇总报告（带通知，支持RSS合并）"""
        summary_type = (
            "当前榜单汇总" if mode_strategy["summary_mode"] == "current" else "当日汇总"
        )
        self.logger.info(f"生成{summary_type}报告...")

        # 加载分析数据
        analysis_data = self._load_analysis_data()
        if not analysis_data:
            return None

        all_results, id_to_name, title_info, new_titles, word_groups, filter_words, global_filters = (
            analysis_data
        )

        # 运行分析流水线
        stats, html_file = await self._run_analysis_pipeline(
            all_results,
            mode_strategy["summary_mode"],
            title_info,
            new_titles,
            word_groups,
            filter_words,
            id_to_name,
            is_daily_summary=True,
            global_filters=global_filters,
            rss_items=rss_items,
            rss_new_items=rss_new_items,
        )

        if html_file:
            self.logger.info(f"{summary_type}报告已生成: {html_file}")

        # 发送通知（合并RSS）
        await self.notification_coordinator.send_notification_if_needed(
            stats=stats,
            report_type=mode_strategy["summary_report_type"],
            mode=mode_strategy["summary_mode"],
            failed_ids=[],
            new_titles=new_titles,
            id_to_name=id_to_name,
            html_file_path=html_file,
            rss_items=rss_items,
            rss_new_items=rss_new_items,
            rss_raw_items=rss_raw_items,
            update_info=self.update_info,
            proxy_url=self.proxy_url,
        )

        return html_file

    async def _generate_summary_html(
        self,
        mode: str = "daily",
        rss_items: Optional[List[Dict]] = None,
        rss_new_items: Optional[List[Dict]] = None,
        rss_raw_items: Optional[List[Dict]] = None,
    ) -> Optional[str]:
        """生成汇总HTML"""
        summary_type = "当前榜单汇总" if mode == "current" else "当日汇总"
        self.logger.info(f"生成{summary_type}HTML...")

        # 加载分析数据（静默模式，避免重复输出日志）
        analysis_data = self._load_analysis_data(quiet=True)
        if not analysis_data:
            return None

        all_results, id_to_name, title_info, new_titles, word_groups, filter_words, global_filters = (
            analysis_data
        )

        # 运行分析流水线（静默模式，避免重复输出日志）
        _, html_file = await self._run_analysis_pipeline(
            all_results,
            mode,
            title_info,
            new_titles,
            word_groups,
            filter_words,
            id_to_name,
            is_daily_summary=True,
            global_filters=global_filters,
            quiet=True,
            rss_items=rss_items,
            rss_new_items=rss_new_items,
        )

        if html_file:
            self.logger.info(f"{summary_type}HTML已生成: {html_file}")
        return html_file

    def _initialize_and_check_config(self) -> None:
        """通用初始化和配置检查"""
        now = self.ctx.get_time()
        self.logger.info(f"当前北京时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")

        if not self.ctx.config["ENABLE_CRAWLER"]:
            self.logger.info("爬虫功能已禁用（ENABLE_CRAWLER=False），程序退出")
            return

        has_notification = self.notification_coordinator.has_notification_configured()
        if not self.ctx.config["ENABLE_NOTIFICATION"]:
            self.logger.info("通知功能已禁用（ENABLE_NOTIFICATION=False），将只进行数据抓取")
        elif not has_notification:
            self.logger.info("未配置任何通知渠道，将只进行数据抓取，不发送通知")
        else:
            self.logger.info("通知功能已启用，将发送通知")

        mode_strategy = self._get_mode_strategy()
        self.logger.info(f"报告模式: {self.report_mode}")
        self.logger.info(f"运行模式: {mode_strategy['description']}")

    async def _crawl_data(self) -> Tuple[Dict, Dict, List]:
        """执行数据爬取 (异步)"""
        ids = []
        for platform in self.ctx.platforms:
            if "name" in platform:
                ids.append((platform["id"], platform["name"]))
            else:
                ids.append(platform["id"])

        self.logger.info(
            f"配置的监控平台: {[p.get('name', p['id']) for p in self.ctx.platforms]}"
        )
        self.logger.info("开始爬取数据 (并发模式)...")
        Path("output").mkdir(parents=True, exist_ok=True)

        results, id_to_name, failed_ids = await self.data_fetcher.crawl_websites(
            ids, self.request_interval
        )

        # 转换为 NewsData 格式并保存到存储后端
        crawl_time = self.ctx.format_time()
        crawl_date = self.ctx.format_date()
        news_data = convert_crawl_results_to_news_data(
            results, id_to_name, failed_ids, crawl_time, crawl_date
        )

        # 保存到存储后端（SQLite）
        if self.storage_manager.save_news_data(news_data):
            self.logger.info(f"数据已保存到存储后端: {self.storage_manager.backend_name}")

        # 触发图片缓存 (异步)
        try:
            image_urls = []
            for src_items in news_data.items.values():
                for item in src_items:
                    if item.image_url:
                        image_urls.append(item.image_url)
            await self._cache_urls(image_urls)
        except Exception as e:
            self.logger.warning(f"[警告] 图片缓存触发失败: {e}")

        # 9. 同步 DuckDB 分析数据
        try:
            self.logger.info("[分析引擎] 正在同步数据到 DuckDB...")
            analytics = self.storage_manager.get_analytics_engine()
            # 使用 asyncio.to_thread 异步执行同步，避免阻塞主线程
            # 注意：sync_data 内部使用了独立的 DuckDB 连接，因此是线程安全的
            await analytics.sync_data_async(days=1)
        except Exception as e:
            self.logger.warning(f"[分析引擎] 同步失败 (非致命): {e}")

        # 保存 TXT 快照（如果启用）
        txt_file = self.storage_manager.save_txt_snapshot(news_data)
        if txt_file:
            self.logger.info(f"TXT 快照已保存: {txt_file}")

        # 兼容：同时保存到原有 TXT 格式（确保向后兼容）
        if self.ctx.config["STORAGE"]["FORMATS"]["TXT"]:
            title_file = self.ctx.save_titles(results, id_to_name, failed_ids)
            self.logger.info(f"标题已保存到: {title_file}")

        return results, id_to_name, failed_ids

    async def _crawl_rss_data(self) -> Tuple[Optional[List[Dict]], Optional[List[Dict]], Optional[List[Dict]]]:
        """
        执行 RSS 数据抓取 (异步包装)

        Returns:
            (rss_stats, rss_new_stats, rss_raw_items) 3-元组：
            - rss_stats: RSS 关键词统计列表
            - rss_new_stats: RSS 新增关键词统计列表
            - rss_raw_items: 原始 RSS 条目列表（用于去重）
        """
        if not self.ctx.rss_enabled:
            return None, None, None

        rss_feeds = self.ctx.rss_feeds
        if not rss_feeds:
            self.logger.info("[RSS] 未配置任何 RSS 源")
            return None, None, None

        try:
            from trendradar.crawler.rss import AsyncRSSFetcher, RSSFeedConfig

            # 构建 RSS 源配置
            feeds = []
            for feed_config in rss_feeds:
                # 读取并验证单个 feed 的 max_age_days（可选）
                max_age_days_raw = feed_config.get("max_age_days")
                max_age_days = None
                if max_age_days_raw is not None:
                    try:
                        max_age_days = int(max_age_days_raw)
                        if max_age_days < 0:
                            feed_id = feed_config.get("id", "unknown")
                            self.logger.warning(f"[RSS] feed '{feed_id}' 的 max_age_days 为负数，将使用全局默认值")
                            max_age_days = None
                    except (ValueError, TypeError):
                        feed_id = feed_config.get("id", "unknown")
                        self.logger.warning(f"[RSS] feed '{feed_id}' 的 max_age_days 格式错误：{max_age_days_raw}")
                        max_age_days = None

                feed = RSSFeedConfig(
                    id=feed_config.get("id", ""),
                    name=feed_config.get("name", ""),
                    url=feed_config.get("url", ""),
                    max_items=feed_config.get("max_items", 50),
                    enabled=feed_config.get("enabled", True),
                    max_age_days=max_age_days,  # None=使用全局，0=禁用，>0=覆盖
                )
                if feed.id and feed.url and feed.enabled:
                    feeds.append(feed)

            if not feeds:
                self.logger.info("[RSS] 没有启用的 RSS 源")
                return None, None

            # 创建抓取器
            rss_config = self.ctx.rss_config
            # RSS 代理：优先使用 RSS 专属代理，否则使用爬虫默认代理
            rss_proxy_url = rss_config.get("PROXY_URL", "") or self.proxy_url or ""
            # 获取配置的时区
            timezone = self.ctx.config.get("TIMEZONE", "Asia/Shanghai")
            # 获取新鲜度过滤配置
            freshness_config = rss_config.get("FRESHNESS_FILTER", {})
            freshness_enabled = freshness_config.get("ENABLED", True)
            default_max_age_days = freshness_config.get("MAX_AGE_DAYS", 3)

            fetcher = AsyncRSSFetcher(
                feeds=feeds,
                request_interval=rss_config.get("REQUEST_INTERVAL", 2000),
                timeout=rss_config.get("TIMEOUT", 15),
                use_proxy=rss_config.get("USE_PROXY", False),
                proxy_url=rss_proxy_url,
                timezone=timezone,
                freshness_enabled=freshness_enabled,
                default_max_age_days=default_max_age_days,
            )

            # 抓取数据
            rss_data = await fetcher.fetch_all()

            # 保存到存储后端
            if self.storage_manager.save_rss_data(rss_data):
                self.logger.info("[RSS] 数据已保存到存储后端")

                # 触发图片缓存 (异步)
                try:
                    image_urls = []
                    for feed_items in rss_data.items.values():
                        for item in feed_items:
                            if item.image_url:
                                image_urls.append(item.image_url)
                    await self._cache_urls(image_urls)
                except Exception as e:
                    self.logger.warning(f"[RSS] 图片缓存触发失败: {e}")

                # 处理 RSS 数据（按模式过滤）并返回用于合并推送

                # 处理 RSS 数据（按模式过滤）并返回用于合并推送
                return self._process_rss_data_by_mode(rss_data)
            else:
                self.logger.error("[RSS] 数据保存失败")
                return None, None, None

        except ImportError as e:
            self.logger.error(f"[RSS] 缺少依赖: {e}")
            self.logger.info("[RSS] 请安装 feedparser: pip install feedparser")
            return None, None, None
        except Exception as e:
            self.logger.error(f"[RSS] 抓取失败: {e}")
            return None, None, None

    def _process_rss_data_by_mode(self, rss_data) -> Tuple[Optional[List[Dict]], Optional[List[Dict]], Optional[List[Dict]]]:
        """
        按报告模式处理 RSS 数据，返回与热榜相同格式的统计结构

        三种模式：
        - daily: 当日汇总，统计=当天所有条目，新增=本次新增条目
        - current: 当前榜单，统计=当前榜单条目，新增=本次新增条目
        - incremental: 增量模式，统计=新增条目，新增=无

        Args:
            rss_data: 当前抓取的 RSSData 对象

        Returns:
            (rss_stats, rss_new_stats, rss_raw_items) 元组：
            - rss_stats: RSS 关键词统计列表（与热榜 stats 格式一致）
            - rss_new_stats: RSS 新增关键词统计列表（与热榜 stats 格式一致）
            - rss_raw_items: 原始 RSS 条目列表（用于去重）
        """
        from trendradar.core.analyzer import count_rss_frequency

        rss_config = self.ctx.rss_config

        # 检查是否启用 RSS 通知
        if not rss_config.get("NOTIFICATION", {}).get("ENABLED", False):
            return None, None, None

        # 加载关键词配置
        try:
            word_groups, filter_words, global_filters = self.ctx.load_frequency_words()
        except FileNotFoundError:
            word_groups, filter_words, global_filters = [], [], []

        timezone = self.ctx.timezone
        max_news_per_keyword = self.ctx.config.get("MAX_NEWS_PER_KEYWORD", 0)
        sort_by_position_first = self.ctx.config.get("SORT_BY_POSITION_FIRST", False)

        rss_stats = None
        rss_new_stats = None

        # 1. 首先获取新增条目（所有模式都需要）
        new_items_dict = self.storage_manager.detect_new_rss_items(rss_data)
        new_items_list = None
        if new_items_dict:
            new_items_list = self._convert_rss_items_to_list(new_items_dict, rss_data.id_to_name)
            if new_items_list:
                self.logger.info(f"[RSS] 检测到 {len(new_items_list)} 条新增")

        # 2. 根据模式获取统计条目
        if self.report_mode == "incremental":
            # 增量模式：统计条目就是新增条目
            if not new_items_list:
                self.logger.info("[RSS] 增量模式：没有新增 RSS 条目")
                return None, None, None

            rss_stats, total = count_rss_frequency(
                rss_items=new_items_list,
                word_groups=word_groups,
                filter_words=filter_words,
                global_filters=global_filters,
                new_items=new_items_list,  # 增量模式所有都是新增
                max_news_per_keyword=max_news_per_keyword,
                sort_by_position_first=sort_by_position_first,
                timezone=timezone,
                rank_threshold=self.rank_threshold,
                quiet=False,
            )
            if not rss_stats:
                self.logger.info("[RSS] 增量模式：关键词匹配后没有内容")
                return None, None, None
            
            # 增量模式下，raw_items 就是 new_items_list
            return rss_stats, None, new_items_list

        elif self.report_mode == "current":
            # 当前榜单模式：统计=当前榜单所有条目
            latest_data = self.storage_manager.get_latest_rss_data(rss_data.date)
            if not latest_data:
                self.logger.info("[RSS] 当前榜单模式：没有 RSS 数据")
                return None, None, None

            all_items_list = self._convert_rss_items_to_list(latest_data.items, latest_data.id_to_name)
            rss_stats, total = count_rss_frequency(
                rss_items=all_items_list,
                word_groups=word_groups,
                filter_words=filter_words,
                global_filters=global_filters,
                new_items=new_items_list,  # 标记新增
                max_news_per_keyword=max_news_per_keyword,
                sort_by_position_first=sort_by_position_first,
                timezone=timezone,
                rank_threshold=self.rank_threshold,
                quiet=False,
            )
            if not rss_stats:
                self.logger.info("[RSS] 当前榜单模式：关键词匹配后没有内容")
                return None, None, None

            # 生成新增统计
            if new_items_list:
                rss_new_stats, _ = count_rss_frequency(
                    rss_items=new_items_list,
                    word_groups=word_groups,
                    filter_words=filter_words,
                    global_filters=global_filters,
                    new_items=new_items_list,
                    max_news_per_keyword=max_news_per_keyword,
                    sort_by_position_first=sort_by_position_first,
                    timezone=timezone,
                    rank_threshold=self.rank_threshold,
                    quiet=True,
                )

        else:
            # daily 模式：统计=当天所有条目
            all_data = self.storage_manager.get_rss_data(rss_data.date)
            if not all_data:
                self.logger.info("[RSS] 当日汇总模式：没有 RSS 数据")
                return None, None, None

            all_items_list = self._convert_rss_items_to_list(all_data.items, all_data.id_to_name)
            rss_stats, total = count_rss_frequency(
                rss_items=all_items_list,
                word_groups=word_groups,
                filter_words=filter_words,
                global_filters=global_filters,
                new_items=new_items_list,  # 标记新增
                max_news_per_keyword=max_news_per_keyword,
                sort_by_position_first=sort_by_position_first,
                timezone=timezone,
                rank_threshold=self.rank_threshold,
                quiet=False,
            )
            if not rss_stats:
                self.logger.info("[RSS] 当日汇总模式：关键词匹配后没有内容")
                return None, None, None

            # 生成新增统计
            if new_items_list:
                rss_new_stats, _ = count_rss_frequency(
                    rss_items=new_items_list,
                    word_groups=word_groups,
                    filter_words=filter_words,
                    global_filters=global_filters,
                    new_items=new_items_list,
                    max_news_per_keyword=max_news_per_keyword,
                    sort_by_position_first=sort_by_position_first,
                    timezone=timezone,
                    rank_threshold=self.rank_threshold,
                    quiet=True,
                )

        return rss_stats, rss_new_stats, all_items_list

    def _convert_rss_items_to_list(self, items_dict: Dict, id_to_name: Dict) -> List[Dict]:
        """将 RSS 条目字典转换为列表格式，并应用新鲜度过滤（用于推送）"""
        rss_items = []
        filtered_count = 0

        # 获取新鲜度过滤配置
        rss_config = self.ctx.rss_config
        freshness_config = rss_config.get("FRESHNESS_FILTER", {})
        freshness_enabled = freshness_config.get("ENABLED", True)
        default_max_age_days = freshness_config.get("MAX_AGE_DAYS", 3)
        timezone = self.ctx.config.get("TIMEZONE", "Asia/Shanghai")

        # 构建 feed_id -> max_age_days 的映射
        feed_max_age_map = {}
        for feed_cfg in self.ctx.rss_feeds:
            feed_id = feed_cfg.get("id", "")
            max_age = feed_cfg.get("max_age_days")
            if max_age is not None:
                try:
                    feed_max_age_map[feed_id] = int(max_age)
                except (ValueError, TypeError):
                    pass

        for feed_id, items in items_dict.items():
            # 确定此 feed 的 max_age_days
            max_days = feed_max_age_map.get(feed_id)
            if max_days is None:
                max_days = default_max_age_days

            for item in items:
                # 应用新鲜度过滤（仅在启用时）
                if freshness_enabled and max_days > 0:
                    if item.published_at and not is_within_days(item.published_at, max_days, timezone):
                        filtered_count += 1
                        continue  # 跳过超过指定天数的文章

                rss_items.append({
                    "title": item.title,
                    "feed_id": feed_id,
                    "feed_name": id_to_name.get(feed_id, feed_id),
                    "url": item.url,
                    "published_at": item.published_at,
                    "summary": item.summary,
                    "author": item.author,
                })

        # 输出过滤统计
        if filtered_count > 0:
            self.logger.info(f"[RSS] 新鲜度过滤：跳过 {filtered_count} 篇旧文章（仍保留在数据库中）")

        return rss_items

    def _filter_rss_by_keywords(self, rss_items: List[Dict]) -> List[Dict]:
        """使用 frequency_words.txt 过滤 RSS 条目"""
        try:
            word_groups, filter_words, global_filters = self.ctx.load_frequency_words()
            if word_groups or filter_words or global_filters:
                from trendradar.core.frequency import matches_word_groups
                filtered_items = []
                for item in rss_items:
                    title = item.get("title", "")
                    if matches_word_groups(title, word_groups, filter_words, global_filters):
                        filtered_items.append(item)

                original_count = len(rss_items)
                rss_items = filtered_items
                self.logger.info(f"[RSS] 关键词过滤后剩余 {len(rss_items)}/{original_count} 条")

                if not rss_items:
                    self.logger.info("[RSS] 关键词过滤后没有匹配内容")
                    return []
        except FileNotFoundError:
            # frequency_words.txt 不存在时跳过过滤
            pass
        return rss_items

    def _generate_rss_html_report(self, rss_items: list, feeds_info: dict) -> str:
        """生成 RSS HTML 报告"""
        try:
            from trendradar.report.rss_html import render_rss_html_content
            from pathlib import Path

            html_content = render_rss_html_content(
                rss_items=rss_items,
                total_count=len(rss_items),
                feeds_info=feeds_info,
                get_time_func=self.ctx.get_time,
            )

            # 保存 HTML 文件
            date_folder = self.ctx.format_date()
            time_filename = self.ctx.format_time()
            output_dir = Path("output") / date_folder / "html"
            output_dir.mkdir(parents=True, exist_ok=True)

            file_path = output_dir / f"rss_{time_filename}.html"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            self.logger.info(f"[RSS] HTML 报告已生成: {file_path}")
            return str(file_path)

        except Exception as e:
            self.logger.error(f"[RSS] 生成 HTML 报告失败: {e}")
            return None

    async def _execute_mode_strategy(
        self, mode_strategy: Dict, results: Dict, id_to_name: Dict, failed_ids: List,
        rss_items: Optional[List[Dict]] = None,
        rss_new_items: Optional[List[Dict]] = None,
    ) -> Optional[str]:
        """执行模式特定逻辑，支持热榜+RSS合并推送"""
        # 获取当前监控平台ID列表
        current_platform_ids = self.ctx.platform_ids

        new_titles = self.ctx.detect_new_titles(current_platform_ids)
        time_info = self.ctx.format_time()
        if self.ctx.config["STORAGE"]["FORMATS"]["TXT"]:
            self.ctx.save_titles(results, id_to_name, failed_ids)
        word_groups, filter_words, global_filters = self.ctx.load_frequency_words()

        # current模式下，实时推送需要使用完整的历史数据来保证统计信息的完整性
        if self.report_mode == "current":
            # 加载完整的历史数据（已按当前平台过滤）
            analysis_data = self._load_analysis_data()
            if analysis_data:
                (
                    all_results,
                    historical_id_to_name,
                    historical_title_info,
                    historical_new_titles,
                    _,
                    _,
                    _,
                ) = analysis_data

                self.logger.info(
                    f"current模式：使用过滤后的历史数据，包含平台：{list(all_results.keys())}"
                )

                stats, html_file = await self._run_analysis_pipeline(
                    all_results,
                    self.report_mode,
                    historical_title_info,
                    historical_new_titles,
                    word_groups,
                    filter_words,
                    historical_id_to_name,
                    failed_ids=failed_ids,
                    global_filters=global_filters,
                    rss_items=rss_items,
                    rss_new_items=rss_new_items,
                )

                combined_id_to_name = {**historical_id_to_name, **id_to_name}

                if html_file:
                    self.logger.info(f"HTML报告已生成: {html_file}")

                # 发送实时通知（使用完整历史数据的统计结果，合并RSS）
                summary_html = None
                if mode_strategy["should_send_realtime"]:
                    await self.notification_coordinator.send_notification_if_needed(
                        stats=stats,
                        report_type=mode_strategy["realtime_report_type"],
                        mode=self.report_mode,
                        failed_ids=failed_ids,
                        new_titles=historical_new_titles,
                        id_to_name=combined_id_to_name,
                        html_file_path=html_file,
                        rss_items=rss_items,
                        rss_new_items=rss_new_items,
                        rss_raw_items=rss_raw_items,
                        update_info=self.update_info,
                        proxy_url=self.proxy_url,
                    )
            else:
                self.logger.error("数据一致性检查失败：保存后立即读取失败")
                raise RuntimeError("数据一致性检查失败：保存后立即读取失败")
        else:
            title_info = self._prepare_current_title_info(results, time_info)
            stats, html_file = await self._run_analysis_pipeline(
                results,
                self.report_mode,
                title_info,
                new_titles,
                word_groups,
                filter_words,
                id_to_name,
                failed_ids=failed_ids,
                global_filters=global_filters,
                rss_items=rss_items,
                rss_new_items=rss_new_items,
            )
            if html_file:
                self.logger.info(f"HTML报告已生成: {html_file}")

            # 发送实时通知（如果需要，合并RSS）
            summary_html = None
            if mode_strategy["should_send_realtime"]:
                await self.notification_coordinator.send_notification_if_needed(
                    stats=stats,
                    report_type=mode_strategy["realtime_report_type"],
                    mode=self.report_mode,
                    failed_ids=failed_ids,
                    new_titles=new_titles,
                    id_to_name=id_to_name,
                    html_file_path=html_file,
                    rss_items=rss_items,
                    rss_new_items=rss_new_items,
                    rss_raw_items=rss_raw_items,
                    update_info=self.update_info,
                    proxy_url=self.proxy_url,
                )

        # 生成汇总报告（如果需要）
        summary_html = None
        if mode_strategy["should_generate_summary"]:
            if mode_strategy["should_send_realtime"]:
                # 如果已经发送了实时通知，汇总只生成HTML不发送通知
                summary_html = await self._generate_summary_html(
                    mode_strategy["summary_mode"],
                    rss_items=rss_items,
                    rss_new_items=rss_new_items,
                    rss_raw_items=rss_raw_items,
                )
            else:
                # daily模式：直接生成汇总报告并发送通知（合并RSS）
                summary_html = await self._generate_summary_report(
                    mode_strategy, 
                    rss_items=rss_items, 
                    rss_new_items=rss_new_items,
                    rss_raw_items=rss_raw_items,
                )

        # 打开浏览器（仅在非容器环境）
        if self._should_open_browser() and html_file:
            if summary_html:
                summary_url = "file://" + str(Path(summary_html).resolve())
                self.logger.info(f"正在打开汇总报告: {summary_url}")
                webbrowser.open(summary_url)
            else:
                file_url = "file://" + str(Path(html_file).resolve())
                self.logger.info(f"正在打开HTML报告: {file_url}")
                webbrowser.open(file_url)
        elif self.is_docker_container and html_file:
            if summary_html:
                self.logger.info(f"汇总报告已生成（Docker环境）: {summary_html}")
            else:
                self.logger.info(f"HTML报告已生成（Docker环境）: {html_file}")

        return summary_html

    async def run(self) -> None:
        """执行分析流程 (异步)"""
        try:
            self._initialize_and_check_config()

            if not self.ctx.config.get("ENABLE_CRAWLER", True):
                # 如果禁用了爬虫，我们仍然可以检查是否有本地历史数据来生成报告
                # 但根据 common 语义，通常是直接退出
                return

            mode_strategy = self._get_mode_strategy()

            # 抓取热榜数据 (异步)
            results, id_to_name, failed_ids = await self._crawl_data()

            # 抓取 RSS 数据 (异步/同步混合)
            rss_stats, rss_new_stats, rss_raw = await self._crawl_rss_data()

            # 执行模式策略，传递 RSS 数据用于合并推送
            await self._execute_mode_strategy(
                mode_strategy, results, id_to_name, failed_ids,
                rss_items=rss_stats, rss_new_items=rss_new_stats,
                rss_raw_items=rss_raw
            )

        except Exception as e:
            self.logger.error(f"分析流程执行出错: {e}", exc_info=True)
            raise
        finally:
            # 清理资源（包括过期数据清理和数据库连接关闭）
            self.ctx.cleanup()
            await self.ctx.aclose()


def main():
    """主程序入口"""
    try:
        analyzer = NewsAnalyzer()
        asyncio.run(analyzer.run())
    except FileNotFoundError as e:
        logger = logging.getLogger("TrendRadar")
        logger.error(f"❌ 配置文件错误: {e}")
    except Exception as e:
        logger = logging.getLogger("TrendRadar")
        logger.error(f"❌ 程序运行错误: {e}")
        raise


if __name__ == "__main__":
    main()