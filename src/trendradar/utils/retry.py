# coding=utf-8
"""
重试机制工具

提供统一的重试装饰器和策略，用于提高系统稳定性。
"""

from functools import wraps
from typing import Callable, Type, Tuple, Any
import time
from trendradar.core.constants import RETRY


def retry_on_exception(
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    max_attempts: int = RETRY.MAX_ATTEMPTS,
    base_wait: float = RETRY.BASE_WAIT_SECONDS,
    max_wait: float = RETRY.MAX_WAIT_SECONDS,
    exponential: bool = True,
):
    """
    重试装饰器

    Args:
        exceptions: 需要重试的异常类型
        max_attempts: 最大重试次数
        base_wait: 基础等待时间（秒）
        max_wait: 最大等待时间（秒）
        exponential: 是否使用指数退避

    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_attempts - 1:  # 不是最后一次尝试
                        if exponential:
                            wait_time = min(base_wait * (2 ** attempt), max_wait)
                        else:
                            wait_time = base_wait
                        
                        time.sleep(wait_time)
            
            # 所有重试都失败，抛出最后一个异常
            raise last_exception
        
        return wrapper
    return decorator


def retry_async_on_exception(
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    max_attempts: int = RETRY.MAX_ATTEMPTS,
    base_wait: float = RETRY.BASE_WAIT_SECONDS,
    max_wait: float = RETRY.MAX_WAIT_SECONDS,
    exponential: bool = True,
):
    """
    异步重试装饰器

    Args:
        exceptions: 需要重试的异常类型
        max_attempts: 最大重试次数
        base_wait: 基础等待时间（秒）
        max_wait: 最大等待时间（秒）
        exponential: 是否使用指数退避

    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            import asyncio
            
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_attempts - 1:  # 不是最后一次尝试
                        if exponential:
                            wait_time = min(base_wait * (2 ** attempt), max_wait)
                        else:
                            wait_time = base_wait
                        
                        await asyncio.sleep(wait_time)
            
            # 所有重试都失败，抛出最后一个异常
            raise last_exception
        
        return wrapper
    return decorator