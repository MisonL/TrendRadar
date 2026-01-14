# coding=utf-8
"""
LLM 服务接口

定义 LLM 服务的抽象接口，用于解耦 context.py 和 llm_service.py 的循环依赖
"""

from abc import ABC, abstractmethod
from typing import Dict, List


class LLMServiceInterface(ABC):
    """LLM 服务接口"""

    @abstractmethod
    async def score_titles(self, titles: List[str]) -> Dict[str, float]:
        """
        批量对标题进行评分

        Args:
            titles: 标题列表

        Returns:
            标题到分数的映射字典 {title: score}
        """
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    def is_enabled(self) -> bool:
        """
        检查 LLM 服务是否启用

        Returns:
            是否启用
        """
        pass

    @abstractmethod
    async def ask(self, prompt: str, system_prompt: str = "You are a helpful assistant.") -> str:
        """
        发送自定义 Prompt 并获取回复

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词

        Returns:
            str: AI 的回复内容
        """
        pass