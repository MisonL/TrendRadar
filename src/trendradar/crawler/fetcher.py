# coding=utf-8
"""
异步数据获取器模块

负责从 NewsNow API 抓取新闻数据，支持并行抓取与并发控制。
"""

import asyncio
import httpx
import json
import random
import logging
from typing import Dict, List, Tuple, Optional, Union

from trendradar.utils.image import is_valid_image_url
from trendradar.utils.image import extract_og_image, extract_main_image
from trendradar.utils.url import normalize_url

logger = logging.getLogger(__name__)

class AsyncDataFetcher:
    """异步数据获取器"""

    # 默认 API 地址
    DEFAULT_API_URL = "https://newsnow.busiyi.world/api/s"

    # 默认请求头
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
    }

    def __init__(
        self,
        proxy_url: Optional[str] = None,
        api_url: Optional[str] = None,
        max_concurrency: int = 10,
        client: Optional[httpx.AsyncClient] = None,
    ):
        """
        初始化数据获取器
        """
        self.proxy_url = proxy_url
        self.api_url = api_url or self.DEFAULT_API_URL
        self.semaphore = asyncio.Semaphore(max_concurrency)
        
        self.client_args = {
            "headers": self.DEFAULT_HEADERS,
            "timeout": 20.0,
            "follow_redirects": True,
        }
        if proxy_url:
            self.client_args["proxy"] = proxy_url
            
        self.client = client

    async def _fetch_wscn_api(self, client: httpx.AsyncClient) -> List[Dict]:
        """专门处理华尔街见闻 API 抓取"""
        url = "https://api-prod.wallstreetcn.com/apiv1/content/fabric/articles/selected?limit=20"
        try:
            resp = await client.get(url, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            items = []
            for article in data.get("data", {}).get("items", []):
                resource = article.get("resource", {})
                title = resource.get("title", article.get("title", ""))
                link = resource.get("uri", article.get("uri", ""))
                image = resource.get("image_uri", article.get("image_uri", ""))
                
                if title:
                    items.append({
                        "title": title,
                        "url": link,
                        "image_url": image
                    })
            return items
        except Exception as e:
            logger.error(f"[Crawler] WSCN API 抓取失败: {e}")
            return []

    async def fetch_data(
        self,
        client: httpx.AsyncClient,
        id_info: Union[str, Tuple[str, str]],
        max_retries: int = 2,
    ) -> Tuple[Optional[str], str, str]:
        """异步获取指定ID数据"""
        if isinstance(id_info, tuple):
            id_value, alias = id_info
        else:
            id_value = id_info
            alias = id_value

        url = f"{self.api_url}?id={id_value}&latest"

        async with self.semaphore:
            for attempt in range(max_retries + 1):
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    
                    # 检查业务逻辑状态
                    try:
                        resp_json = response.json()
                        if isinstance(resp_json, dict) and resp_json.get("status") == "error":
                            logger.error(f"接口返回错误 ({id_value}): {resp_json.get('message', '未知错误')}")
                            return None, id_value, alias
                    except Exception:
                        # 非 JSON 或解析失败，按原始文本处理
                        pass
                        
                    return response.text, id_value, alias
                except Exception as e:
                    if attempt < max_retries:
                        await asyncio.sleep(1.0 * (attempt + 1))
                    else:
                        logger.error(f"请求 {id_value} 失败: {e}")
        return None, id_value, alias

    async def crawl_websites(
        self,
        ids_list: List[Union[str, Tuple[str, str]]],
        request_interval: int = 100,
    ) -> Tuple[Dict, Dict, List]:
        """并发抓取多个平台数据"""
        results = {}
        id_to_name = {}
        failed_ids = []

        # 准备 ID 映射
        for id_info in ids_list:
            if isinstance(id_info, tuple):
                id_to_name[id_info[0]] = id_info[1]
            else:
                id_to_name[id_info] = id_info

        # 分类 ID
        normal_ids = []
        for id_info in ids_list:
            p_id = id_info[0] if isinstance(id_info, tuple) else id_info
            if p_id == "wscn":
                if self.client:
                    wscn_items = await self._fetch_wscn_api(self.client)
                else:
                    async with httpx.AsyncClient(**self.client_args) as client:
                        wscn_items = await self._fetch_wscn_api(client)
                
                if wscn_items:
                    results["wscn"] = {}
                    for i, item in enumerate(wscn_items):
                        results["wscn"][item["title"]] = {
                            "ranks": [i + 1],
                            "url": item["url"],
                            "mobileUrl": item["url"],
                            "image_url": item["image_url"]
                        }
                else:
                    failed_ids.append("wscn")
            else:
                normal_ids.append(id_info)

        # 抓取通用平台
        if normal_ids:
            if self.client:
                responses = await asyncio.gather(*[self.fetch_data(self.client, i) for i in normal_ids])
            else:
                async with httpx.AsyncClient(**self.client_args) as client:
                    responses = await asyncio.gather(*[self.fetch_data(client, i) for i in normal_ids])
            
            for text, p_id, _ in responses:
                if not text:
                    failed_ids.append(p_id)
                    continue
                try:
                    data = json.loads(text)
                    results[p_id] = {}
                    for idx, item in enumerate(data.get("items", []), 1):
                        title = str(item.get("title", "")).strip()
                        if not title: continue
                        url = item.get("url", "")
                        if title in results[p_id]:
                             results[p_id][title]["ranks"].append(idx)
                        else:
                             results[p_id][title] = {
                                 "ranks": [idx],
                                 "url": url,
                                 "mobileUrl": item.get("mobileUrl", ""),
                                 "image_url": item.get("pic") or item.get("img") or ""
                             }
                except Exception as e:
                    logger.error(f"解析 {p_id} 失败: {e}")
                    failed_ids.append(p_id)

        # 补充图片
        await self._enrich_images(results)
        return results, id_to_name, failed_ids

    async def _enrich_images(self, results: Dict) -> None:
        """为 Top 条目补充图片"""
        tasks = []
        for p_id, items in results.items():
            sorted_items = sorted(items.items(), key=lambda x: min(x[1]["ranks"]) if x[1]["ranks"] else 999)
            for title, info in sorted_items[:5]:
                if not info.get("image_url") and info.get("url"):
                    tasks.append(self._fetch_and_set_image(p_id, title, info["url"], results))
        
        if tasks:
            logger.info(f"[爬虫] 补充 {len(tasks)} 条图片...")
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _fetch_and_set_image(self, p_id: str, title: str, url: str, results: Dict) -> None:
        """补充单个条目的图片"""
        try:
            # WSCN 特殊处理 (API 获取详情)
            if "wallstreetcn.com/articles/" in url:
                article_id = url.split("/articles/")[-1].split("?")[0]
                api = f"https://api-prod.wallstreetcn.com/apiv1/content/articles/{article_id}?extract=0"
                async with httpx.AsyncClient(**self.client_args) as client:
                    resp = await client.get(api)
                    if resp.status_code == 200:
                        data = resp.json().get("data", {})
                        img = data.get("image_uri")
                        if img:
                             results[p_id][title]["image_url"] = img
                             return

            # 通用处理
            async with httpx.AsyncClient(**self.client_args) as client:
                await asyncio.sleep(random.uniform(0.1, 0.5))
                resp = await client.get(url, follow_redirects=True)
                if resp.status_code == 200:
                    img = extract_og_image(resp.text) or extract_main_image(resp.text, url)
                    if img:
                        results[p_id][title]["image_url"] = img
        except Exception:
            pass