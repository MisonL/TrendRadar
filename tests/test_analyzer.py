# coding=utf-8
"""
分析引擎测试
"""

import pytest
from trendradar.core.analyzer import (
    calculate_news_weight,
    WordFrequencyConfig,
)
from trendradar.core.constants import WEIGHT


class TestCalculateNewsWeight:
    """测试 calculate_news_weight 函数"""

    def test_weight_calculation_with_ranks(self):
        """测试有排名的权重计算"""
        title_data = {
            "ranks": [1, 2, 3],
            "count": 3,
        }

        weight = calculate_news_weight(
            title_data,
            rank_threshold=5,
            weight_config={
                "RANK_WEIGHT": WEIGHT.DEFAULT_RANK_WEIGHT,
                "FREQUENCY_WEIGHT": WEIGHT.DEFAULT_FREQUENCY_WEIGHT,
                "HOTNESS_WEIGHT": WEIGHT.DEFAULT_HOTNESS_WEIGHT,
            }
        )

        # 验证权重在合理范围内
        assert 0 <= weight <= 1000

    def test_weight_calculation_no_ranks(self):
        """测试无排名的权重计算"""
        title_data = {
            "ranks": [],
            "count": 0,
        }

        weight = calculate_news_weight(
            title_data,
            rank_threshold=5,
            weight_config={
                "RANK_WEIGHT": WEIGHT.DEFAULT_RANK_WEIGHT,
                "FREQUENCY_WEIGHT": WEIGHT.DEFAULT_FREQUENCY_WEIGHT,
                "HOTNESS_WEIGHT": WEIGHT.DEFAULT_HOTNESS_WEIGHT,
            }
        )

        # 无排名时权重应为 0
        assert weight == 0.0

    def test_weight_calculation_custom_weights(self):
        """测试自定义权重配置"""
        title_data = {
            "ranks": [1, 2, 3],
            "count": 3,
        }

        # 使用自定义权重
        custom_weight = calculate_news_weight(
            title_data,
            rank_threshold=5,
            weight_config={
                "RANK_WEIGHT": 0.5,
                "FREQUENCY_WEIGHT": 0.3,
                "HOTNESS_WEIGHT": 0.2,
            }
        )

        # 验证权重计算成功
        assert custom_weight >= 0


class TestWordFrequencyConfig:
    """测试 WordFrequencyConfig 类"""

    def test_config_creation(self):
        """测试配置创建"""
        config = WordFrequencyConfig(
            word_groups=[{"word": "测试"}],
            filter_words=["过滤词"],
            id_to_name={"id1": "平台1"}
        )

        assert config.word_groups == [{"word": "测试"}]
        assert config.filter_words == ["过滤词"]
        assert config.id_to_name == {"id1": "平台1"}
        assert config.rank_threshold == 3  # 新默认值是 3

    def test_config_defaults(self):
        """测试配置默认值"""
        config = WordFrequencyConfig(
            word_groups=[],
            filter_words=[],
            id_to_name={}
        )

        # 验证默认值
        assert config.mode == "daily"
        assert config.max_news_per_keyword == 0
        assert config.sort_by_position_first is False
        assert config.quiet is False

    def test_config_weight_config_default(self):
        """测试权重配置默认值"""
        config = WordFrequencyConfig(
            word_groups=[],
            filter_words=[],
            id_to_name={}
        )

        # 验证权重配置默认值
        assert config.weight_config is not None
        assert "RANK_WEIGHT" in config.weight_config
        assert "FREQUENCY_WEIGHT" in config.weight_config
        assert "HOTNESS_WEIGHT" in config.weight_config


def test_helper_functions():
    """测试辅助函数"""
    from trendradar.core.frequency import _parse_word

    # 测试普通词
    result = _parse_word("测试")
    assert result["word"] == "测试"
    assert result["is_regex"] is False

    # 测试正则表达式
    result = _parse_word("/test.*/")
    assert result["is_regex"] is True
    assert "pattern" in result

    # 测试显示名称
    result = _parse_word("word => 显示名称")
    assert result["word"] == "word"
    assert result["display_name"] == "显示名称"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])