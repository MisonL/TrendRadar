# coding=utf-8
"""
通知协调模块

负责处理通知发送逻辑、推送窗口检查、去重和频率限制。
将复杂的通知逻辑从 NewsAnalyzer 中剥离。
"""

import logging
from datetime import datetime, time
from typing import Dict, List, Optional, Any

class NotificationCoordinator:
    """通知协调类"""

    def __init__(
        self,
        config: Dict[str, Any],
        storage_manager: Any,
        notification_dispatcher: Any,
        push_manager: Any,
        ctx: Any
    ):
        self.config = config
        self.storage_manager = storage_manager
        self.notification_dispatcher = notification_dispatcher
        self.push_manager = push_manager
        self.ctx = ctx
        self.logger = logging.getLogger("TrendRadar.Notification")

    def has_notification_configured(self) -> bool:
        """检查是否配置了任何通知渠道"""
        cfg = self.config
        return any(
            [
                cfg.get("FEISHU_WEBHOOK_URL"),
                cfg.get("DINGTALK_WEBHOOK_URL"),
                cfg.get("WEWORK_WEBHOOK_URL"),
                (cfg.get("TELEGRAM_BOT_TOKEN") and cfg.get("TELEGRAM_CHAT_ID")),
                (
                    cfg.get("EMAIL_FROM")
                    and cfg.get("EMAIL_PASSWORD")
                    and cfg.get("EMAIL_TO")
                ),
                (cfg.get("NTFY_SERVER_URL") and cfg.get("NTFY_TOPIC")),
                cfg.get("BARK_URL"),
                cfg.get("SLACK_WEBHOOK_URL"),
            ]
        )

    def _has_valid_content(
        self, mode: str, stats: List[Dict], new_titles: Optional[Dict] = None
    ) -> bool:
        """检查是否有有效的新闻内容"""
        if mode == "incremental":
            has_new_titles = bool(
                new_titles and any(len(titles) > 0 for titles in new_titles.values())
            )
            has_matched_news = any(stat["count"] > 0 for stat in stats) if stats else False
            return has_new_titles and has_matched_news
        elif mode == "current":
            return any(stat["count"] > 0 for stat in stats) if stats else False
        else:
            has_matched_news = any(stat["count"] > 0 for stat in stats) if stats else False
            has_new_news = bool(
                new_titles and any(len(titles) > 0 for titles in new_titles.values())
            )
            return has_matched_news or has_new_news

    async def send_notification_if_needed(
        self,
        stats: List[Dict],
        report_type: str,
        mode: str,
        failed_ids: Optional[List[str]] = None,
        new_titles: Optional[Dict] = None,
        id_to_name: Optional[Dict] = None,
        html_file_path: Optional[str] = None,
        rss_items: Optional[List[Dict]] = None,
        rss_new_items: Optional[List[Dict]] = None,
        rss_raw_items: Optional[List[Dict]] = None,
        update_info: Optional[Dict] = None,
        proxy_url: Optional[str] = None,
    ) -> bool:
        """统一的通知发送逻辑"""
        has_notification = self.has_notification_configured()
        cfg = self.config

        # 检查是否有有效内容（热榜或RSS）
        has_news_content = self._has_valid_content(mode, stats, new_titles)
        has_rss_content = bool(rss_items and len(rss_items) > 0)
        has_any_content = has_news_content or has_rss_content

        # 计算条目数
        news_count = sum(len(stat.get("titles", [])) for stat in stats) if stats else 0
        rss_count = len(rss_items) if rss_items else 0

        if not (cfg.get("ENABLE_NOTIFICATION", True) and has_notification and has_any_content):
            self._log_skip_reason(report_type, mode, has_notification, has_any_content, has_rss_content, new_titles)
            return False

        # 输出统计
        content_parts = []
        if news_count > 0:
            content_parts.append(f"热榜 {news_count} 条")
        if rss_count > 0:
            content_parts.append(f"RSS {rss_count} 条")
        self.logger.info(f"[推送] 准备发送：{' + '.join(content_parts)}，合计 {news_count + rss_count} 条")

        # 窗口控制
        if cfg.get("PUSH_WINDOW", {}).get("ENABLED"):
            time_start = cfg["PUSH_WINDOW"]["TIME_RANGE"]["START"]
            time_end = cfg["PUSH_WINDOW"]["TIME_RANGE"]["END"]
            if not self.push_manager.is_in_time_range(time_start, time_end):
                self.logger.info(f"推送窗口控制：不在时间窗口 {time_start}-{time_end} 内，跳过")
                return False
            if cfg["PUSH_WINDOW"].get("ONCE_PER_DAY") and self.push_manager.has_pushed_today():
                self.logger.info("推送窗口控制：今天已推送过，跳过")
                return False

        # 准备数据
        report_data = self.ctx.prepare_report(stats, failed_ids, new_titles, id_to_name, mode)

        # 去重
        filtered_report_data, items_to_record = self.ctx.deduplicate_report_data(report_data)
        
        # RSS 去重 (使用原始数据)
        if rss_raw_items:
            filtered_rss_raw_items, rss_items_to_record = self.ctx.deduplicate_rss_data(rss_raw_items)
            # 只有当有新的 RSS 条目时，才认为 RSS 有内容
            has_new_rss = len(filtered_rss_raw_items) > 0
            # 注意: 如果所有 raw items 都是重复的，那么 rss_items (stats) 即使有内容也不应该触发通知，
            # 或者应该提示用户"没有新内容"。但目前的 stats 可能包含了旧内容。
            # 简单起见，我们仅记录新条目，并用 has_new_rss 控制 "跳过本次推送" 的逻辑。
        else:
            # Fallback (兼容旧逻辑，但这是错误的路径，会报 warning 或者保留原状)
            # 既然是修复，我们假设调用方会传 rss_raw_items
            filtered_rss_raw_items, rss_items_to_record = [], []
            has_new_rss = False
            if rss_items:
                self.logger.warning("[去重] 收到 RSS 统计但未收到原始 items，跳过 RSS 去重逻辑")

        items_to_record.extend(rss_items_to_record)

        # 去重后检查
        has_filtered_news = any(len(s["titles"]) > 0 for s in filtered_report_data.get("stats", []))
        has_filtered_rss = has_new_rss
        
        if cfg.get("NOTIFICATION", {}).get("deduplication", {}).get("enabled", False):
            if not has_filtered_news and not has_filtered_rss:
                self.logger.info("[去重] 所有新闻和 RSS 均已推送过，跳过本次推送")
                return False
            
            if not has_filtered_news:
                 self.logger.info("[去重] 热榜新闻均已推送过，仅推送新增 RSS")
            elif not has_filtered_rss and rss_items:
                 self.logger.info("[去重] RSS 均已推送过，仅推送热榜新闻")

        # 最终分发
        try:
             results = self.notification_dispatcher.dispatch_all(
                report_data=filtered_report_data,
                report_type=report_type,
                update_info=update_info,
                proxy_url=proxy_url,
                mode=mode,
                html_file_path=html_file_path,
                rss_items=rss_items,
                rss_new_items=rss_new_items,
            )

             if results and any(results.values()):
                 if items_to_record:
                     self.ctx.record_pushed_items(items_to_record)
                 if cfg.get("PUSH_WINDOW", {}).get("ENABLED") and cfg["PUSH_WINDOW"].get("ONCE_PER_DAY"):
                     self.push_manager.record_push(report_type)
                 return True
             
             return False
        except Exception as e:
            self.logger.error(f"通知发送失败: {e}", exc_info=True)
            return False

    def _log_skip_reason(self, report_type: str, mode: str, has_notification: bool, has_any_content: bool, has_rss: bool, new_titles: Optional[Dict]):
        """记录跳过通知的原因"""
        if not self.config.get("ENABLE_NOTIFICATION", True):
            self.logger.info(f"跳过{report_type}通知：通知功能已禁用")
            return
        if not has_notification:
            self.logger.warning("⚠️ 警告：通知功能已启用但未配置任何渠道")
            return
        if not has_any_content:
            if "实时" in report_type:
                if mode == "incremental":
                    has_new = bool(new_titles and any(len(t) > 0 for t in new_titles.values()))
                    if not has_new and not has_rss:
                        self.logger.info("跳过实时推送通知：增量模式下未检测到新增新闻和RSS")
                    elif not has_new:
                        self.logger.info("跳过实时推送通知：增量模式下新增新闻未匹配到关键词")
                else:
                    self.logger.info(f"跳过实时推送通知：{mode}模式下未匹配到热点")
            else:
                 self.logger.info(f"跳过{report_type}通知：未匹配到有效内容")