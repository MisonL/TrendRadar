# coding=utf-8
"""
爬虫模块测试
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from trendradar.crawler.fetcher import AsyncDataFetcher


@pytest.fixture
def mock_http_client():
    """创建模拟的 HTTP 客户端"""
    client = AsyncMock()
    return client


@pytest.fixture
def fetcher():
    """创建 AsyncDataFetcher 实例"""
    return AsyncDataFetcher(
        proxy_url=None,
        max_concurrency=10
    )


class TestAsyncDataFetcher:
    """测试 AsyncDataFetcher 类"""

    @pytest.mark.asyncio
    async def test_fetch_data_success(self, fetcher, mock_http_client):
        """测试成功获取数据"""
        # 模拟响应
        mock_response = AsyncMock()
        mock_response.text = '{"status": "success", "data": {"title": "测试新闻"}}'
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_http_client.get = AsyncMock(return_value=mock_response)

        # 执行测试
        data_text, id_value, alias = await fetcher.fetch_data(
            mock_http_client,
            ("test_id", "测试平台"),
            max_retries=2
        )

        # 验证结果
        assert data_text is not None
        assert id_value == "test_id"
        assert alias == "测试平台"

    @pytest.mark.asyncio
    async def test_fetch_data_retry_on_failure(self, fetcher, mock_http_client):
        """测试失败后重试"""
        # 模拟第一次失败，第二次成功
        mock_response = AsyncMock()
        mock_response.text = '{"status": "success", "data": {"title": "测试新闻"}}'
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        # 第一次调用抛出异常，第二次返回成功
        mock_http_client.get = AsyncMock(side_effect=[Exception("网络错误"), mock_response])

        # 执行测试
        data_text, id_value, alias = await fetcher.fetch_data(
            mock_http_client,
            ("test_id", "测试平台"),
            max_retries=2
        )

        # 验证结果
        assert data_text is not None
        assert mock_http_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_fetch_data_max_retries_exceeded(self, fetcher, mock_http_client):
        """测试超过最大重试次数"""
        # 模拟持续失败
        mock_http_client.get = AsyncMock(side_effect=Exception("网络错误"))

        # 执行测试
        data_text, id_value, alias = await fetcher.fetch_data(
            mock_http_client,
            ("test_id", "测试平台"),
            max_retries=2
        )

        # 验证结果
        assert data_text is None
        assert mock_http_client.get.call_count == 3  # 初始 + 2次重试

    @pytest.mark.asyncio
    async def test_fetch_data_invalid_status(self, fetcher, mock_http_client):
        """测试响应状态无效"""
        # 模拟响应状态为失败
        mock_response = AsyncMock()
        mock_response.text = '{"status": "error", "message": "请求失败"}'
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_http_client.get = AsyncMock(return_value=mock_response)

        # 执行测试
        data_text, id_value, alias = await fetcher.fetch_data(
            mock_http_client,
            ("test_id", "测试平台"),
            max_retries=2
        )

        # 验证结果
        assert data_text is None

    def test_concurrency_control(self, fetcher):
        """测试并发控制"""
        # 验证信号量已正确设置
        assert fetcher.semaphore is not None
        assert fetcher.semaphore._value == 10  # max_concurrency

    def test_client_args(self, fetcher):
        """测试客户端参数"""
        # 验证客户端参数已正确设置
        assert "headers" in fetcher.client_args
        assert "timeout" in fetcher.client_args
        assert fetcher.client_args["timeout"] == 20.0


@pytest.mark.asyncio
async def test_concurrent_fetch():
    """测试并发获取多个数据源"""
    fetcher = AsyncDataFetcher(
        proxy_url=None,
        max_concurrency=5
    )

    # 模拟多个数据源
    sources = [
        ("id1", "平台1"),
        ("id2", "平台2"),
        ("id3", "平台3"),
    ]

    # 模拟响应
    mock_response = AsyncMock()
    mock_response.text = '{"status": "success", "data": {"title": "测试新闻"}}'
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    with patch('trendradar.crawler.fetcher.httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # 执行并发获取
        results = []
        async with mock_client_class.return_value:
            for source_id, alias in sources:
                result = await fetcher.fetch_data(
                    mock_client,
                    (source_id, alias),
                    max_retries=1
                )
                results.append(result)

        # 验证结果
        assert len(results) == 3
        assert all(r[0] is not None for r in results)  # 所有数据都成功获取


if __name__ == "__main__":
    pytest.main([__file__, "-v"])