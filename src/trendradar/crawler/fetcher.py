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
import httpx
import asyncio
import sys

from trendradar.utils.image import is_valid_image_url
from trendradar.utils.image import extract_og_image, extract_main_image

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

        Args:
            proxy_url: 代理服务器 URL（可选）
            api_url: API 基础 URL（可选）
            max_concurrency: 最大并发数
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

    async def fetch_data(
        self,
        client: httpx.AsyncClient,
        id_info: Union[str, Tuple[str, str]],
        max_retries: int = 2,
    ) -> Tuple[Optional[str], str, str]:
        """
        异步获取指定ID数据

        使用更精细的异常处理，区分不同类型的错误

        Returns:
            (响应文本, 平台ID, 别名)
        """
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

                    data_text = response.text
                    data_json = json.loads(data_text)

                    status = data_json.get("status", "未知")
                    if status not in ["success", "cache"]:
                        raise ValueError(f"响应状态异常: {status}")

                    return data_text, id_value, alias

                except httpx.TimeoutException as e:
                    # 超时错误：立即重试
                    logger.warning(f"请求 {id_value} 超时 (重试 {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries:
                        wait_time = 1.0 + attempt  # 短等待时间
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"请求 {id_value} 最终超时失败: {e}")
                        return None, id_value, alias

                except httpx.ConnectError as e:
                    # 连接错误：指数退避
                    logger.warning(f"请求 {id_value} 连接失败 (重试 {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries:
                        wait_time = 2 ** attempt  # 指数退避
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"请求 {id_value} 最终连接失败: {e}")
                        return None, id_value, alias

                except httpx.NetworkError as e:
                    # 网络错误：指数退避
                    logger.warning(f"请求 {id_value} 网络错误 (重试 {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries:
                        wait_time = 2 ** attempt
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"请求 {id_value} 最终网络错误: {e}")
                        return None, id_value, alias

                except httpx.HTTPStatusError as e:
                    # HTTP 错误：4xx 不重试，5xx 重试
                    status_code = e.response.status_code
                    logger.warning(f"请求 {id_value} HTTP 错误 {status_code}: {e}")

                    if 400 <= status_code < 500:
                        # 4xx 错误不重试（客户端错误）
                        logger.error(f"请求 {id_value} 客户端错误 {status_code}，不重试")
                        return None, id_value, alias
                    elif 500 <= status_code < 600:
                        # 5xx 错误重试（服务器错误）
                        if attempt < max_retries:
                            wait_time = 2 ** attempt
                            await asyncio.sleep(wait_time)
                        else:
                            logger.error(f"请求 {id_value} 最终服务器错误 {status_code}")
                            return None, id_value, alias

                except json.JSONDecodeError as e:
                    # JSON 解析错误：不重试
                    logger.error(f"请求 {id_value} JSON 解析失败: {e}")
                    return None, id_value, alias

                except ValueError as e:
                    # 响应状态异常：不重试
                    logger.error(f"请求 {id_value} 响应状态异常: {e}")
                    return None, id_value, alias

                except Exception as e:
                    # 其他未知错误：记录详细日志并重试
                    logger.error(f"请求 {id_value} 未知错误 (重试 {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries:
                        wait_time = random.uniform(1, 3) + attempt
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"请求 {id_value} 最终失败: {e}")
                        return None, id_value, alias

        return None, id_value, alias

    async def crawl_websites(
        self,
        ids_list: List[Union[str, Tuple[str, str]]],
        request_interval: int = 100,
    ) -> Tuple[Dict, Dict, List]:
        """
        并发抓取多个平台数据
        """
        results = {}
        id_to_name = {}
        failed_ids = []

        # 准备 ID 映射
        for id_info in ids_list:
            if isinstance(id_info, tuple):
                id_to_name[id_info[0]] = id_info[1]
            else:
                id_to_name[id_info] = id_info

        # 并发执行
        if self.client:
            tasks = [self.fetch_data(self.client, id_str) for id_str in ids_list]
            responses = await asyncio.gather(*tasks)
        else:
            async with httpx.AsyncClient(**self.client_args) as client:
                tasks = [self.fetch_data(client, id_str) for id_str in ids_list]
                responses = await asyncio.gather(*tasks)

        # 解析结果
        for data_text, id_value, alias in responses:
            if not data_text:
                failed_ids.append(id_value)
                continue
                
            try:
                data = json.loads(data_text)
                results[id_value] = {}
                
                # 遍历条目并去重/格式化
                for index, item in enumerate(data.get("items", []), 1):
                    title = item.get("title")
                    if not title or not str(title).strip():
                        continue
                        
                    title = str(title).strip()
                    url = item.get("url", "")
                    mobile_url = item.get("mobileUrl", "")

                    if title in results[id_value]:
                        results[id_value][title]["ranks"].append(index)
                    else:
                        results[id_value][title] = {
                            "ranks": [index],
                            "url": url,
                            "mobileUrl": mobile_url,
                            "image_url": "",
                        }
                    
                    # 提取封面图
                    image_url = item.get("pic") or item.get("img") or item.get("cover") or item.get("thumbnail")
                    if image_url and is_valid_image_url(image_url):
                        results[id_value][title]["image_url"] = image_url
            
            except Exception as e:
                logger.error(f"处理 {id_value} 数据出错: {e}")
                failed_ids.append(id_value)

        # 二次处理：为 Top 5 且没有图片的条目抓取 og:image
        # 为了不拖慢整体速度，限制并发和数量
        tasks_enrich = []
        
        async def fetch_and_extract_og(source_id, title, target_url):
            try:
                # 针对 WallstreetCN 的特殊处理 (SPA 无法直接提取)
                if "wallstreetcn.com/articles/" in target_url:
                    try:
                        article_id = target_url.split("/articles/")[-1].split("?")[0]
                        api_url = f"https://api-prod.wallstreetcn.com/apiv1/content/articles/{article_id}?extract=0"
                        
                        if self.client:
                            resp = await self.client.get(api_url)
                        else:
                            async with httpx.AsyncClient(**self.client_args) as client:
                                resp = await client.get(api_url)
                                
                        if resp.status_code == 200:
                            data = resp.json().get("data", {})
                            # 优先使用封面图
                            img_url = data.get("image_uri")
                            
                            # 如果没有封面图，尝试从内容中提取
                            if not img_url and data.get("content"):
                                img_url = extract_main_image(data["content"], target_url)
                                
                            if img_url:
                                logger.info(f"[爬虫] WSCN API 提取成功 [{source_id}] {title[:10]}... => {img_url}")
                                results[source_id][title]["image_url"] = img_url
                                return
                    except Exception as e:
                        logger.warning(f"[爬虫] WSCN API 提取失败: {e}")
                        # 失败后继续尝试通用方法（虽然大概率也会失败）

                # 通用逻辑
                # 随机User-Agent避免被反爬
                headers = self.DEFAULT_HEADERS.copy()
                
                # 增加随机延时
                await asyncio.sleep(random.uniform(0.1, 0.5))
                
                if self.client:
                    resp = await self.client.get(target_url, headers=headers, follow_redirects=True)
                else:
                    async with httpx.AsyncClient(**self.client_args) as client:
                        resp = await client.get(target_url, headers=headers, follow_redirects=True)
                
                if resp.status_code == 200:
                    # 优先尝试 og:image
                    img_url = extract_og_image(resp.text)
                    
                    # 回退尝试提取正文第一张大图
                    if not img_url:
                        img_url = extract_main_image(resp.text, target_url)

                    if img_url:
                        logger.info(f"[爬虫] 成功提取图片 [{source_id}] {title[:10]}... => {img_url}")
                        results[source_id][title]["image_url"] = img_url
                    else:
                        logger.warning(f"[爬虫] 未提取到图片 [{source_id}] {title[:10]}... URL: {target_url} Status: {resp.status_code}")
                else:
                    logger.error(f"[爬虫] 请求失败 [{source_id}] {title[:10]}... URL: {target_url} Status: {resp.status_code}")
            except Exception as e:
                # 忽略单个页面抓取错误
                pass

        for source_id, items_dict in results.items():
            # items_dict: {title: {ranks: [1], ...}}
            sorted_items = sorted(items_dict.items(), key=lambda x: min(x[1]["ranks"]) if x[1]["ranks"] else 999)
            
            count = 0
            for title, info in sorted_items:
                if count >= 5:
                    break
                
                if not info.get("image_url") and info.get("url"):
                    tasks_enrich.append(fetch_and_extract_og(source_id, title, info["url"]))
                    count += 1
        
        if tasks_enrich:
            logger.info(f"[爬虫] 正在为 {len(tasks_enrich)} 个热门条目补充图片...")
            # 使用现有信号量或新信号量限制并发
            # 为了避免长时间阻塞，使用 wait_for
            try:
                await asyncio.wait_for(asyncio.gather(*tasks_enrich), timeout=15.0)
            except asyncio.TimeoutError:
                logger.warning("[爬虫] 图片补充任务部分超时")
            except Exception as e:
                logger.error(f"图片补充任务出错: {e}")

        return results, id_to_name, failed_ids
