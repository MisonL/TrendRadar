# coding=utf-8
"""
TrendRadar 常量定义

统一管理所有魔法数字和配置常量，提高代码可维护性。
"""

from dataclasses import dataclass


@dataclass
class WeightConstants:
    """权重计算常量"""
    MAX_RANK_SCORE: int = 10
    BASE_RANK_SCORE: int = 11
    FREQUENCY_MULTIPLIER: int = 10
    HOTNESS_MULTIPLIER: int = 100
    
    # 默认权重配置
    DEFAULT_RANK_WEIGHT: float = 0.4
    DEFAULT_FREQUENCY_WEIGHT: float = 0.3
    DEFAULT_HOTNESS_WEIGHT: float = 0.3


@dataclass
class BatchConstants:
    """批次大小常量"""
    DEFAULT_BATCH_SIZE: int = 4000
    DINGTALK_BATCH_SIZE: int = 20000
    FEISHU_BATCH_SIZE: int = 30000
    WEWORK_BATCH_SIZE: int = 4000
    TELEGRAM_BATCH_SIZE: int = 4000
    NTFY_BATCH_SIZE: int = 3800
    BARK_BATCH_SIZE: int = 3600
    SLACK_BATCH_SIZE: int = 4000
    EMAIL_BATCH_SIZE: int = 29000
    DEFAULT_BATCH_INTERVAL: float = 1.0


@dataclass
class TimeoutConstants:
    """超时时间常量"""
    HTTP_REQUEST_TIMEOUT: int = 30
    CRAWLER_REQUEST_TIMEOUT: int = 15
    LLM_REQUEST_TIMEOUT: int = 30
    SMTP_CONNECTION_TIMEOUT: int = 10


@dataclass
class RetryConstants:
    """重试策略常量"""
    MAX_ATTEMPTS: int = 3
    BASE_WAIT_SECONDS: float = 1.0
    MAX_WAIT_SECONDS: float = 10.0


@dataclass
class CacheConstants:
    """缓存配置常量"""
    LLM_CACHE_SIZE: int = 1000
    REGEX_CACHE_SIZE: int = 100
    IMAGE_CACHE_TTL: int = 86400  # 24小时


@dataclass
class ConcurrencyConstants:
    """并发控制常量"""
    RSS_MAX_CONCURRENCY: int = 5
    HTTP_MAX_CONNECTIONS: int = 100
    HTTP_MAX_KEEPALIVE: int = 20


@dataclass
class RankingConstants:
    """排名相关常量"""
    DEFAULT_RANK: int = 99
    DEFAULT_RANK_THRESHOLD: int = 3


@dataclass
class MessageSizeLimits:
    """消息大小限制"""
    NTFY_MAX: int = 4096  # 4KB
    BARK_MAX: int = 4096  # 4KB


# 全局常量实例
WEIGHT = WeightConstants()
BATCH = BatchConstants()
TIMEOUT = TimeoutConstants()
RETRY = RetryConstants()
CACHE = CacheConstants()
CONCURRENCY = ConcurrencyConstants()
RANKING = RankingConstants()
MESSAGE_SIZE = MessageSizeLimits()