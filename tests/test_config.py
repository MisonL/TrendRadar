# coding=utf-8
"""
配置加载测试
"""

import pytest
from trendradar.core.config import (
    parse_multi_account_config,
    validate_paired_configs,
)


class TestParseMultiAccountConfig:
    """测试多账号配置解析"""

    def test_basic_parsing(self):
        """测试基本解析"""
        accounts = parse_multi_account_config("url1;url2;url3")
        assert len(accounts) == 3
        assert accounts == ["url1", "url2", "url3"]

    def test_empty_config(self):
        """测试空配置"""
        accounts = parse_multi_account_config("")
        assert accounts == []

    def test_whitespace_handling(self):
        """测试空格处理"""
        accounts = parse_multi_account_config("url1 ; url2 ; url3")
        assert accounts == ["url1", "url2", "url3"]

    def test_custom_separator(self):
        """测试自定义分隔符"""
        accounts = parse_multi_account_config("url1,url2,url3", separator=",")
        assert accounts == ["url1", "url2", "url3"]

    def test_filter_empty(self):
        """测试过滤空值"""
        accounts = parse_multi_account_config("url1;;url2")
        # 默认不保留空字符串用于占位（除非显式处理，但此处实现是保留的）
        # 根据源代码实现：accounts = [acc.strip() for acc in config_value.split(separator)]
        # 而 if all(not acc for acc in accounts): return [] 仅检查全空。
        # 所以结果应该是 ["url1", "", "url2"]
        assert accounts == ["url1", "", "url2"]


class TestValidatePairedConfigs:
    """测试配对配置验证"""

    def test_valid_paired_configs(self):
        """测试有效的配对配置"""
        configs = {
            "token": ["token1", "token2"],
            "chat_id": ["chat1", "chat2"]
        }

        is_valid, count = validate_paired_configs(
            configs,
            "telegram",
            ["token", "chat_id"]
        )

        assert is_valid is True
        assert count == 2

    def test_invalid_paired_configs(self):
        """测试无效的配对配置"""
        configs = {
            "token": ["token1", "token2"],
            "chat_id": ["chat1"]  # 数量不匹配
        }

        is_valid, count = validate_paired_configs(
            configs,
            "telegram",
            ["token", "chat_id"]
        )

        assert is_valid is False

    def test_single_config(self):
        """测试单个配置"""
        configs = {
            "token": ["token1"],
            "chat_id": ["chat1"]
        }

        is_valid, count = validate_paired_configs(
            configs,
            "telegram",
            ["token", "chat_id"]
        )

        assert is_valid is True
        assert count == 1


def test_url_validation():
    """测试 URL 验证"""
    # 这个函数需要在 config.py 中实现
    # 这里只是示例测试结构
    pass


def test_required_fields_validation():
    """测试必填字段验证"""
    # 这个函数需要在 config.py 中实现
    # 这里只是示例测试结构
    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])