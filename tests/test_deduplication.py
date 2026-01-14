# coding=utf-8
"""
去重逻辑测试
"""

import pytest
from unittest.mock import MagicMock, patch
from trendradar.context import AppContext


@pytest.fixture
def mock_config():
    """创建模拟配置"""
    return {
        "NOTIFICATION": {
            "deduplication": {
                "enabled": True,
                "use_url_hash": True
            }
        },
        "app": {
            "timezone": "Asia/Shanghai"
        }
    }


@pytest.fixture
def sample_report_data():
    """创建示例报告数据"""
    return {
        "stats": [
            {
                "word": "测试",
                "count": 2,
                "titles": [
                    {
                        "title": "测试新闻1",
                        "url": "https://example.com/1",
                        "source_id": "source1",
                        "source_name": "平台1"
                    },
                    {
                        "title": "测试新闻2",
                        "url": "https://example.com/2",
                        "source_id": "source1",
                        "source_name": "平台1"
                    }
                ]
            }
        ],
        "new_titles": {
            "source1": {
                "测试新闻1": {
                    "url": "https://example.com/1"
                }
            }
        }
    }


class TestDeduplication:
    """测试去重逻辑"""

    def test_content_hash_generation(self, mock_config):
        """测试内容哈希生成"""
        with patch('trendradar.context.get_storage_manager') as mock_get_storage:
            mock_storage = MagicMock()
            mock_get_storage.return_value = mock_storage

            context = AppContext(mock_config)

            # 测试基于 URL 的哈希
            hash1 = context.get_content_hash(
                "https://example.com/1",
                "测试新闻1",
                "source1"
            )
            hash2 = context.get_content_hash(
                "https://example.com/1",
                "测试新闻1",
                "source1"
            )
            hash3 = context.get_content_hash(
                "https://example.com/2",
                "测试新闻2",
                "source1"
            )

            # 相同内容应该生成相同的哈希
            assert hash1 == hash2
            # 不同内容应该生成不同的哈希
            assert hash1 != hash3

    def test_deduplication_disabled(self, mock_config, sample_report_data):
        """测试去重功能禁用"""
        mock_config["NOTIFICATION"]["deduplication"]["enabled"] = False

        with patch('trendradar.context.get_storage_manager') as mock_get_storage:
            mock_storage = MagicMock()
            mock_get_storage.return_value = mock_storage

            context = AppContext(mock_config)
            filtered_data, items_to_record = context.deduplicate_report_data(sample_report_data)

            # 去重禁用时，数据应该保持不变
            assert filtered_data == sample_report_data
            assert len(items_to_record) == 0

    def test_batch_query_optimization(self, mock_config, sample_report_data):
        """测试批量查询优化"""
        with patch('trendradar.context.get_storage_manager') as mock_get_storage:
            mock_storage = MagicMock()

            # 模拟批量查询返回所有 hash 都未推送
            mock_storage.is_news_pushed_batch.return_value = {
                "hash1": False,
                "hash2": False,
                "hash3": False
            }

            mock_get_storage.return_value = mock_storage

            context = AppContext(mock_config)
            filtered_data, items_to_record = context.deduplicate_report_data(sample_report_data)

            # 验证批量查询被调用
            assert mock_storage.is_news_pushed_batch.called

            # 验证结果
            assert len(items_to_record) == 3  # 两条新闻 + 一条新增新闻 = 3

    def test_deduplicate_rss_data(self, mock_config):
        """测试 RSS 数据去重"""
        rss_items = [
            {
                "title": "RSS新闻1",
                "url": "https://example.com/rss1",
                "feed_id": "feed1"
            },
            {
                "title": "RSS新闻2",
                "url": "https://example.com/rss2",
                "feed_id": "feed1"
            }
        ]

        with patch('trendradar.context.get_storage_manager') as mock_get_storage:
            mock_storage = MagicMock()

            # 模拟批量查询返回第一条已推送，第二条未推送
            mock_storage.is_news_pushed_batch.return_value = {
                "hash1": True,
                "hash2": False
            }

            mock_get_storage.return_value = mock_storage

            context = AppContext(mock_config)

            # 生成 hash
            rss_items_with_hash = []
            for item in rss_items:
                item["hash"] = context.get_content_hash(
                    item["url"],
                    item["title"],
                    item["feed_id"]
                )
                rss_items_with_hash.append(item)

            # 重新设置批量查询返回值
            mock_storage.is_news_pushed_batch.return_value = {
                rss_items_with_hash[0]["hash"]: True,
                rss_items_with_hash[1]["hash"]: False
            }

            filtered_items, items_to_record = context.deduplicate_rss_data(rss_items_with_hash)

            # 验证结果
            assert len(filtered_items) == 1  # 只有一条未推送
            assert len(items_to_record) == 1


def test_record_pushed_items():
    """测试记录已推送条目"""
    # 测试批量记录功能
    items = [
        {"hash": "hash1", "title": "标题1", "url": "https://example.com/1"},
        {"hash": "hash2", "title": "标题2", "url": "https://example.com/2"},
    ]

    with patch('trendradar.context.get_storage_manager') as mock_get_storage:
        mock_storage = MagicMock()
        mock_storage.record_pushed_news.return_value = True
        mock_get_storage.return_value = mock_storage

        config = {
            "NOTIFICATION": {
                "deduplication": {"enabled": True}
            },
            "app": {"timezone": "Asia/Shanghai"}
        }

        context = AppContext(config)
        context.record_pushed_items(items)

        # 验证每条记录都被调用
        assert mock_storage.record_pushed_news.call_count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])