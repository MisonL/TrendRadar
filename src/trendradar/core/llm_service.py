# coding=utf-8
"""
LLM 服务模块

提供统一的 LLM 接口，支持 Ollama 和 OpenAI 兼容协议。
用于对新闻标题进行评分、分类和摘要。
"""

import json
import logging
from typing import List, Dict
import httpx

from trendradar.core.llm_interface import LLMServiceInterface

logger = logging.getLogger(__name__)


class LLMService(LLMServiceInterface):
    """LLM 服务类"""

    DEFAULT_PROMPT_TEMPLATE = """
你是一个专业的新闻编辑。请对以下新闻标题进行评分 (0-10分)。
评分标准：
- 高分 (8-10): 重大科技突破、行业重磅新闻、具有深远影响的事件。
- 中分 (5-7): 普通行业动态、新品发布、常规资讯。
- 低分 (0-4): 标题党、广告营销、无实质内容、无关紧要的琐事。

请以 JSON 格式输出，key 为新闻 ID (顺序号)，value 为评分。

新闻列表：
{news_list}

输出格式示例：
{{
    "0": 8.5,
    "1": 3.0,
    "2": 6.5
}}
只能输出合法的 JSON 字符串，不要包含 Markdown 格式标记或其他废话。
"""

    def __init__(self, config: Dict):
        """
        初始化 LLM 服务

        Args:
            config: 配置字典，包含 LLM 相关配置
        """
        self.config = config.get("LLM", {})
        
        self.enabled = self.config.get("enabled", False)
        self.provider = self.config.get("provider", "ollama")
        self.base_url = self.config.get("base_url", "http://localhost:11434")
        self.api_key = self.config.get("api_key", "sk-placeholder")
        self.model = self.config.get("model", "qwen2.5:7b")
        self.batch_size = self.config.get("batch_size", 10)
        
        # 针对不同提供商调整 API 路径
        if self.provider == "ollama":
            if not self.base_url.rstrip("/").endswith("/v1"):
                self.base_url = f"{self.base_url.rstrip('/')}/v1"
        elif self.provider == "openai":
            if not self.base_url:
               self.base_url = "https://api.openai.com/v1"

    async def score_titles(self, titles: List[str]) -> Dict[str, float]:
        """
        批量对标题进行评分
        
        Args:
            titles: 标题列表
            
        Returns:
            Dict[str, float]: 标题 -> 分数 的映射
        """
        if not self.enabled or not titles:
            return {t: 0.0 for t in titles}

        scores = {}
        total = len(titles)
        
        # 分批处理
        for i in range(0, total, self.batch_size):
            batch = titles[i : i + self.batch_size]
            batch_scores = await self._process_batch(batch)
            scores.update(batch_scores)
            
        return scores

    async def _process_batch(self, batch_titles: List[str]) -> Dict[str, float]:
        """处理单个批次"""
        # 构建带 ID 的输入列表
        indexed_titles = {str(i): title for i, title in enumerate(batch_titles)}
        news_list_str = "\n".join([f"[{i}] {t}" for i, t in enumerate(batch_titles)])
        
        prompt = self.config.get("prompt_template") or self.DEFAULT_PROMPT_TEMPLATE
        prompt = prompt.format(news_list=news_list_str)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant that outputs JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"}  # 尝试强制 JSON 模式
                }

                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                
                # 解析 JSON
                try:
                    # 尝试清理可能的 Markdown 标记
                    cleaned_content = content.replace("```json", "").replace("```", "").strip()
                    parsed = json.loads(cleaned_content)
                    
                    batch_result = {}
                    for idx_str, score in parsed.items():
                        if idx_str in indexed_titles:
                            title = indexed_titles[idx_str]
                            batch_result[title] = float(score)
                    
                    # 补全解析失败的
                    for title in batch_titles:
                        if title not in batch_result:
                            batch_result[title] = 5.0 # 解析失败给默认分
                            
                    return batch_result
                    
                except json.JSONDecodeError:
                    print(f"[LLM] JSON 解析失败: {content[:100]}...")
                    return {t: 5.0 for t in batch_titles}

        except Exception as e:
            print(f"[LLM] 请求失败: {e}")
            return {t: 5.0 for t in batch_titles}

    async def filter_titles_by_score(
        self,
        titles: List[str],
        threshold: float
    ) -> List[str]:
        """
        根据分数过滤标题

        Args:
            titles: 标题列表
            threshold: 分数阈值，低于此分数的标题将被过滤

        Returns:
            过滤后的标题列表
        """
        if not self.enabled or not titles:
            return titles

        scores = await self.score_titles(titles)
        filtered = [t for t in titles if scores.get(t, 0.0) >= threshold]

        logger.info(f"[LLM] 过滤前: {len(titles)} 条, 过滤后: {len(filtered)} 条 (阈值: {threshold})")

        return filtered

    async def ask(self, prompt: str, system_prompt: str = "You are a helpful assistant.") -> str:
        """
        发送自定义 Prompt 并获取回复
        
        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            
        Returns:
            str: AI 的回复内容
        """
        if not self.enabled:
            return "LLM service is disabled."

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.7,
                }

                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                
                result = response.json()
                return result["choices"][0]["message"]["content"]

        except Exception as e:
            return f"LLM Request failed: {e}"

    def is_enabled(self) -> bool:
        """
        检查 LLM 服务是否启用

        Returns:
            是否启用
        """
        return self.enabled
