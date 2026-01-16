# coding=utf-8
"""
Image Cache Module

Handles downloading, storing, and serving cached images to prevent hotlinking issues
and ensure image availability.
"""

import logging
import asyncio
import hashlib
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


class ImageCache:
    """图片缓存管理器"""

    # 只允许缓存的图片类型
    ALLOWED_MIME_TYPES = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
        "image/tiff": ".tiff",
    }

    # 默认请求头
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }

    def __init__(
        self,
        cache_dir: str = "output/cache/images",
        retention_days: int = 30,
        max_concurrent_downloads: int = 10,
        timeout: int = 15,
        client: Optional[httpx.AsyncClient] = None,
    ):
        """
        初始化图片缓存管理器

        Args:
            cache_dir: 缓存目录
            retention_days: 图片保留天数
            max_concurrent_downloads: 最大并发下载数
            timeout: 下载超时时间（秒）
        """
        self.base_dir = Path(cache_dir)
        self.retention_days = retention_days
        self.timeout = timeout
        self.client = client
        
        # 并发控制
        self.semaphore = asyncio.Semaphore(max_concurrent_downloads)
        
        # 确保目录存在
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_cache_path(self, url: str) -> Path:
        """
        获取缓存文件路径
        
        为了避免单个目录下文件过多，使用二级目录结构：
        output/cache/images/YYYY-MM-DD/md5_hash.ext
        
        注意：这里返回默认路径，实际下载时可能会根据 Content-Type 调整扩展名
        """
        url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
        today = datetime.now().strftime("%Y-%m-%d")
        day_dir = self.base_dir / today
        day_dir.mkdir(parents=True, exist_ok=True)
        
        # 默认使用 .jpg，如果已存在文件则返回实际存在的
        default_path = day_dir / f"{url_hash}.jpg"
        
        # 检查是否已存在（任何扩展名）
        existing = self.find_existing_cache(url)
        if existing:
            return existing
            
        return default_path

    def find_existing_cache(self, url: str) -> Optional[Path]:
        """查找已存在的缓存文件（遍历所有日期目录）"""
        url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
        
        # 优化：优先检查最近几天的目录
        today = datetime.now()
        for i in range(self.retention_days + 1):
            date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            day_dir = self.base_dir / date_str
            if not day_dir.exists():
                continue
                
            for ext in self.ALLOWED_MIME_TYPES.values():
                path = day_dir / f"{url_hash}{ext}"
                if path.exists():
                    return path
        return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=5))
    async def download(self, url: str) -> Optional[str]:
        """
        异步下载图片并缓存

        Args:
            url: 图片 URL

        Returns:
            缓存文件的相对路径（str），如果下载失败返回 None
        """
        if not url:
            return None

        # 检查是否已缓存
        existing = self.find_existing_cache(url)
        if existing:
            return str(existing.resolve().relative_to(Path.cwd()))

        async with self.semaphore:
            try:
                # 准备路径（预设 .jpg，后面根据 header 修正）
                url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
                today_str = datetime.now().strftime("%Y-%m-%d")
                save_dir = self.base_dir / today_str
                save_dir.mkdir(parents=True, exist_ok=True)
                
                if self.client:
                    response = await self.client.get(url, headers=self.DEFAULT_HEADERS)
                else:
                    async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                        response = await client.get(url, headers=self.DEFAULT_HEADERS)

                response.raise_for_status()
                
                # 检查 Content-Type
                content_type = response.headers.get("Content-Type", "").lower().split(";")[0].strip()
                if content_type not in self.ALLOWED_MIME_TYPES:
                    logging.getLogger('TrendRadar').info(f"[ImageCache] 跳过不支持的图片类型: {content_type} ({url})")
                    return None
                
                # 确定扩展名
                ext = self.ALLOWED_MIME_TYPES[content_type]
                # 有些服务器通过 Content-Disposition 返回文件名
                
                # 生成最终保存路径
                file_path = save_dir / f"{url_hash}{ext}"
                
                # 写入文件
                content = response.content
                with open(file_path, "wb") as f:
                    f.write(content)
                    
                return str(file_path.resolve().relative_to(Path.cwd()))
                    
            except httpx.HTTPStatusError as e:
                # 检查响应状态 (如果 response 未定义，如 client 连接异常，这里会报错，但 tenacity 会重试)
                if hasattr(e, 'response') and e.response.status_code == 404:
                    logging.getLogger('TrendRadar').info(f"[ImageCache] 图片不存在 (404): {url}")
                    return None # 404 不重试
                logging.getLogger('TrendRadar').info(f"[ImageCache] 下载失败 ({getattr(e.response, 'status_code', 'unknown')}): {url}")
                raise # 其他错误让 tenacity 重试
            except Exception as e:
                logging.getLogger('TrendRadar').info(f"[ImageCache] 下载异常: {e} ({url})")
                raise

    def cleanup(self) -> int:
        """
        清理过期图片

        Returns:
            清理的文件/目录数量
        """
        if self.retention_days <= 0:
            return 0
            
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        deleted_count = 0
        
        # 遍历日期目录
        for item in self.base_dir.iterdir():
            if not item.is_dir():
                continue
                
            try:
                dir_date = datetime.strptime(item.name, "%Y-%m-%d")
                if dir_date < cutoff_date:
                    shutil.rmtree(item)
                    deleted_count += 1
                    logging.getLogger('TrendRadar').info(f"[ImageCache] 删除过期图片目录: {item.name}")
            except ValueError:
                # 非日期命名的目录，跳过
                continue
                
        return deleted_count

    async def get_cached_url(self, original_url: str, base_url: str = "") -> str:
        """
        获取缓存后的 URL（如果可用），否则返回原始 URL

        Args:
            original_url: 原始图片链接
            base_url: 静态服务的基准 URL（如 /images 或 http://mcp-server/images）

        Returns:
            缓存后的 URL 或原始 URL
        """
        if not original_url:
            return ""

        # 尝试查找或下载
        local_path = await self.download(original_url)
        if not local_path:
            return original_url
            
        # 转换为 URL 路径
        # local_path 如 output/cache/images/2026-01-13/hash.jpg
        # 如果 base_url 为 /images，则应返回 /images/2026-01-13/hash.jpg
        # 这里假设 base_url 映射到了 output/cache/images
        
        path_obj = Path(local_path)
        try:
            rel_path = path_obj.relative_to(self.base_dir)
            # 统一使用正斜杠
            rel_path_str = str(rel_path).replace(os.sep, "/")
            if base_url:
                if base_url.endswith("/"):
                    return f"{base_url}{rel_path_str}"
                return f"{base_url}/{rel_path_str}"
            return rel_path_str
        except ValueError:
            return original_url