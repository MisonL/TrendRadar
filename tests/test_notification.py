# coding=utf-8
"""
通知模块测试
"""

import pytest
from trendradar.notification.senders import SendConfig, ChannelSender


@pytest.fixture
def sample_config():
    """创建示例配置"""
    return {
        "webhook_url": "https://example.com/webhook",
        "report_data": {
            "stats": [
                {
                    "word": "测试",
                    "count": 5,
                    "titles": [
                        {"title": "测试新闻1", "url": "https://example.com/1"},
                        {"title": "测试新闻2", "url": "https://example.com/2"},
                    ]
                }
            ]
        },
        "report_type": "daily",
        "mode": "daily",
    }


class TestSendConfig:
    """测试 SendConfig 类"""

    def test_send_config_creation(self):
        """测试 SendConfig 创建"""
        config = SendConfig(
            webhook_url="https://example.com/webhook",
            report_data={"stats": []},
            report_type="daily"
        )

        assert config.webhook_url == "https://example.com/webhook"
        assert config.report_type == "daily"
        assert config.batch_size == 4000  # 默认值

    def test_send_config_with_optional_fields(self):
        """测试带可选字段的 SendConfig"""
        config = SendConfig(
            webhook_url="https://example.com/webhook",
            report_data={"stats": []},
            report_type="daily",
            account_label="账号1",
            batch_size=2000
        )

        assert config.account_label == "账号1"
        assert config.batch_size == 2000


class TestChannelSender:
    """测试 ChannelSender 抽象类"""

    def test_channel_sender_is_abstract(self):
        """测试 ChannelSender 是抽象类"""
        with pytest.raises(TypeError):
            ChannelSender(
                SendConfig(
                    webhook_url="https://example.com/webhook",
                    report_data={"stats": []},
                    report_type="daily"
                )
            )


@pytest.mark.asyncio
async def test_multi_account_parsing():
    """测试多账号配置解析"""
    from trendradar.core.config import parse_multi_account_config

    # 测试分号分隔
    accounts = parse_multi_account_config("url1;url2;url3")
    assert len(accounts) == 3
    assert accounts[0] == "url1"
    assert accounts[1] == "url2"
    assert accounts[2] == "url3"

    # 测试空配置
    accounts = parse_multi_account_config("")
    assert len(accounts) == 0

    # 测试空格处理
    accounts = parse_multi_account_config("url1 ; url2 ; url3")
    assert len(accounts) == 3


def test_content_splitting():
    """测试内容分批"""
    from trendradar.notification.splitter import split_content_into_batches

    # 测试短内容（不需要分批）
    report_data = {"stats": [], "new_titles": [], "failed_ids": []}
    batches = split_content_into_batches(report_data, "feishu", max_bytes=4000)
    assert len(batches) == 1

    # 测试长内容（需要分批）
    long_stats = {
        "stats": [{"word": f"词{i}", "count": 1, "titles": [{"title": "标题"*200, "url": "url"}]} for i in range(100)],
        "new_titles": [],
        "failed_ids": []
    }
    batches = split_content_into_batches(long_stats, "feishu", max_bytes=4000, max_notify_news=0)
    assert len(batches) > 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])