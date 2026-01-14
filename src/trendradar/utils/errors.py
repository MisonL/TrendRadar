# coding=utf-8
"""
TrendRadar 自定义异常类型

提供统一的异常类型体系，便于错误处理和调试。
"""


class TrendRadarError(Exception):
    """TrendRadar 基类异常"""
    pass


class CrawlerError(TrendRadarError):
    """爬虫异常"""
    pass


class FetchError(CrawlerError):
    """数据获取失败异常"""
    pass


class ParseError(CrawlerError):
    """数据解析失败异常"""
    pass


class NetworkError(CrawlerError):
    """网络连接异常"""
    pass


class TimeoutError(CrawlerError):
    """请求超时异常"""
    pass


class HTTPError(CrawlerError):
    """HTTP 错误异常"""
    def __init__(self, status_code: int, message: str = ""):
        self.status_code = status_code
        self.message = message
        super().__init__(f"HTTP {status_code}: {message}")


class StorageError(TrendRadarError):
    """存储异常"""
    pass


class NotificationError(TrendRadarError):
    """通知异常"""
    pass


class ConfigError(TrendRadarError):
    """配置异常"""
    pass


class LLMError(TrendRadarError):
    """LLM 服务异常"""
    pass


class ValidationError(TrendRadarError):
    """验证异常"""
    pass


class DataNotFoundError(TrendRadarError):
    """数据未找到异常"""
    pass


class InvalidParameterError(TrendRadarError):
    """无效参数异常"""
    pass