# coding=utf-8
"""
缓存工具

提供内存缓存和装饰器支持，用于优化性能。
"""

import hashlib
import json
from functools import lru_cache
from typing import Any, Optional, Callable, TypeVar, Dict

from trendradar.core.constants import CACHE


T = TypeVar('T')


class SimpleCache:
    """简单内存缓存"""

    def __init__(self, max_size: int = 1000):
        self._cache: Dict[str, Any] = {}
        self._max_size = max_size

    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        return self._cache.get(key)

    def set(self, key: str, value: Any) -> None:
        """设置缓存"""
        if len(self._cache) >= self._max_size:
            # 简单的 LRU：删除第一个
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = value

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()


def cache_key(*args, **kwargs) -> str:
    """生成缓存键"""
    key_data = {
        "args": args,
        "kwargs": sorted(kwargs.items())
    }
    return hashlib.md5(json.dumps(key_data, sort_keys=True).encode()).hexdigest()


def memoize(maxsize: int = CACHE.LLM_CACHE_SIZE):
    """自定义缓存装饰器"""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        cache = SimpleCache(maxsize)

        def wrapper(*args, **kwargs) -> T:
            key = cache_key(*args, **kwargs)
            result = cache.get(key)

            if result is None:
                result = func(*args, **kwargs)
                cache.set(key, result)

            return result

        wrapper.cache_clear = cache.clear
        wrapper.cache_info = lambda: {"size": len(cache._cache), "maxsize": maxsize}

        return wrapper

    return decorator


# 正则表达式缓存
@lru_cache(maxsize=CACHE.REGEX_CACHE_SIZE)
def compile_regex(pattern: str, flags: int = 0):
    """编译正则表达式（带缓存）"""
    import re
    return re.compile(pattern, flags)