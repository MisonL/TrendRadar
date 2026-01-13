# coding=utf-8
"""
图片处理工具模块

提供从 HTML 内容中提取正文图片的功能，支持：
- 提取正文第一张合规大图
- 过滤广告图片（基于关键词和域名黑名单）
- 过滤无效图片（图标、像素点等）
- 提供默认 Banner 图片
"""

import re
import html
from typing import Optional, List
from urllib.parse import urlparse, urljoin

# 广告/无效图片关键词黑名单
AD_KEYWORDS = [
    "ad", "ads", "advert", "banner", "promotion", "spread", "pixel", "tracker",
    "logo", "icon", "share", "avatar", "qrcode", "weixin_code", "button",
    "placeholder", "transparent", "loading", "spinner", "1x1", "googleads",
    "doubleclick", "facebook", "twitter", "linkedin", "weibo", "friend_feed",
    "recommend", "related", "footer", "header", "nav", "menu", "sidebar"
]

# 广告/无效域名黑名单
AD_DOMAINS = [
    "ad.doubleclick.net",
    "googleads.g.doubleclick.net",
    "pagead2.googlesyndication.com",
    "tpc.googlesyndication.com",
    "stats.g.doubleclick.net",
    "adservice.google.com",
    "securepubads.g.doubleclick.net",
    "pixel.facebook.com",
    "analytics.twitter.com",
    "p.weibo.com",
    "hm.baidu.com",
    "mmbiz.qpic.cn/mmbiz_png/0",  # 微信空白图
]

# 默认 Banner 图片（当无法提取到有效图片时使用）
# 选用一张科技感较强的通用背景图
DEFAULT_BANNER_URL = "https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=900&q=80"


def is_valid_image_url(url: str) -> bool:
    """
    检查图片 URL 是否有效且不是广告

    Args:
        url: 图片链接

    Returns:
        是否有效
    """
    if not url:
        return False

    url_lower = url.lower()
    
    # 1. 检查文件扩展名（如果是明显的非图片资源）
    if url_lower.endswith(('.js', '.css', '.html', '.htm', '.json')):
        return False

    # 2. 检查关键词黑名单
    for keyword in AD_KEYWORDS:
        # 使用更严格的匹配，避免误杀（例如 "upload" 包含 "ad"）
        if f"{keyword}." in url_lower or \
           f"/{keyword}/" in url_lower or \
           f"_{keyword}_" in url_lower or \
           f"-{keyword}-" in url_lower or \
           f"={keyword}" in url_lower:
            return False

    # 3. 检查域名黑名单
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        for ad_domain in AD_DOMAINS:
            if ad_domain in domain:
                return False
    except:
        return False

    # 4. 过滤 Data URI
    if url_lower.startswith('data:'):
        return False

    return True


def extract_main_image(content: str, base_url: str = "") -> str:
    """
    从 HTML 内容中提取正文第一张有效大图

    Args:
        content: HTML 内容或文本
        base_url: 基础 URL，用于补全相对路径

    Returns:
        提取到的图片 URL，如果没有则返回空字符串
    """
    if not content:
        return ""

    # 解码 HTML 实体
    content = html.unescape(content)

    # 1. 正则匹配 img 标签
    # 匹配 src 属性，同时也尝试匹配 data-src (常见的懒加载属性)
    img_pattern = re.compile(r'<img[^>]+(?:src|data-src)=["\']([^"\']+)["\'][^>]*>', re.IGNORECASE)
    
    matches = img_pattern.findall(content)
    
    for img_url in matches:
        img_url = img_url.strip()
        
        # 补全相对路径
        if base_url and not img_url.startswith(('http://', 'https://', 'data:')):
            try:
                img_url = urljoin(base_url, img_url)
            except:
                continue

        # 检查图片有效性
        if is_valid_image_url(img_url):
            return img_url

    # 2. 如果没有 img 标签，尝试匹配 markdown 图片语法 ![...](url)
    md_pattern = re.compile(r'!\[.*?\]\((https?://[^)]+)\)', re.IGNORECASE)
    md_matches = md_pattern.findall(content)
    
    for img_url in md_matches:
        if is_valid_image_url(img_url):
            return img_url

    return ""


def get_default_banner() -> str:
    """获取默认 Banner 图片"""
    return DEFAULT_BANNER_URL
