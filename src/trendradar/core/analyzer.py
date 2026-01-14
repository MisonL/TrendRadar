# coding=utf-8
"""
统计分析模块

提供新闻统计和分析功能：
- calculate_news_weight: 计算新闻权重
- format_time_display: 格式化时间显示
- count_word_frequency: 统计词频
"""

from typing import Dict, List, Tuple, Optional, Callable
from dataclasses import dataclass, field

from trendradar.core.frequency import matches_word_groups, _word_matches
from trendradar.core.constants import WEIGHT, RANKING


@dataclass
class WordFrequencyConfig:
    """词频统计配置"""
    word_groups: List[Dict]
    filter_words: List[str]
    id_to_name: Dict
    title_info: Optional[Dict] = None
    rank_threshold: int = RANKING.DEFAULT_RANK_THRESHOLD
    new_titles: Optional[Dict] = None
    mode: str = "daily"
    global_filters: Optional[List[str]] = None
    weight_config: Optional[Dict] = None
    max_news_per_keyword: int = 0
    sort_by_position_first: bool = False
    is_first_crawl_func: Optional[Callable[[], bool]] = None
    convert_time_func: Optional[Callable[[str], str]] = None
    quiet: bool = False
    
    # 运行时属性
    is_first_today: bool = field(init=False)
    
    def __post_init__(self):
        if self.weight_config is None:
            self.weight_config = {
                "RANK_WEIGHT": WEIGHT.DEFAULT_RANK_WEIGHT,
                "FREQUENCY_WEIGHT": WEIGHT.DEFAULT_FREQUENCY_WEIGHT,
                "HOTNESS_WEIGHT": WEIGHT.DEFAULT_HOTNESS_WEIGHT,
            }
        
        if self.convert_time_func is None:
            self.convert_time_func = lambda x: x
        
        if self.is_first_crawl_func is None:
            self.is_first_crawl_func = lambda: True
        
        self.is_first_today = self.is_first_crawl_func()


def calculate_news_weight(
    title_data: Dict,
    rank_threshold: int,
    weight_config: Dict,
) -> float:
    """
    计算新闻权重，用于排序

    权重公式: Score = (Rank * W1) + (Frequency * W2) + (Hotness * W3)

    Args:
        title_data: 标题数据，包含 ranks 和 count
        rank_threshold: 排名阈值
        weight_config: 权重配置 {RANK_WEIGHT, FREQUENCY_WEIGHT, HOTNESS_WEIGHT}

    Returns:
        float: 计算出的权重值
    """
    ranks = title_data.get("ranks", [])
    if not ranks:
        return 0.0

    count = int(title_data.get("count", len(ranks)))

    # 排名权重：Σ(BASE_RANK_SCORE - min(rank, MAX_RANK_SCORE)) / 出现次数
    rank_weight = _calculate_rank_weight(ranks)

    # 频次权重：min(出现次数, MAX_RANK_SCORE) × FREQUENCY_MULTIPLIER
    frequency_weight = _calculate_frequency_weight(count)

    # 热度加成：高排名次数 / 总出现次数 × HOTNESS_MULTIPLIER
    hotness_weight = _calculate_hotness_weight(ranks, rank_threshold)

    total_weight = (
        rank_weight * weight_config.get("RANK_WEIGHT", WEIGHT.DEFAULT_RANK_WEIGHT)
        + frequency_weight * weight_config.get("FREQUENCY_WEIGHT", WEIGHT.DEFAULT_FREQUENCY_WEIGHT)
        + hotness_weight * weight_config.get("HOTNESS_WEIGHT", WEIGHT.DEFAULT_HOTNESS_WEIGHT)
    )

    return total_weight


def _calculate_rank_weight(ranks: List[int]) -> float:
    """计算排名权重"""
    rank_scores = [
        WEIGHT.BASE_RANK_SCORE - min(int(rank), WEIGHT.MAX_RANK_SCORE)
        for rank in ranks
    ]
    return sum(rank_scores) / len(ranks) if ranks else 0


def _calculate_frequency_weight(count: int) -> float:
    """计算频次权重"""
    return min(count, WEIGHT.MAX_RANK_SCORE) * WEIGHT.FREQUENCY_MULTIPLIER


def _calculate_hotness_weight(ranks: List[int], rank_threshold: int) -> float:
    """计算热度权重"""
    if not ranks:
        return 0.0
    
    high_rank_count = sum(1 for rank in ranks if rank <= rank_threshold)
    hotness_ratio = high_rank_count / len(ranks)
    return hotness_ratio * WEIGHT.HOTNESS_MULTIPLIER


def _determine_processing_scope(config: WordFrequencyConfig, results: Dict) -> Tuple[Dict, bool]:
    """确定处理的数据源和新增标记逻辑"""
    if config.mode == "incremental":
        if config.is_first_today:
            return results, True
        else:
            return config.new_titles if config.new_titles else {}, True
    elif config.mode == "current":
        return _filter_current_batch(config, results), False
    else:  # daily
        return results, False


def _filter_current_batch(config: WordFrequencyConfig, results: Dict) -> Dict:
    """过滤当前时间批次的新闻（current 模式）"""
    if not config.title_info:
        return results
    
    # 找到最新时间
    latest_time = None
    for source_titles in config.title_info.values():
        for title_data in source_titles.values():
            last_time = title_data.get("last_time", "")
            if last_time and (latest_time is None or last_time > latest_time):
                latest_time = last_time
    
    if not latest_time:
        return results
    
    # 只处理 last_time 等于最新时间的新闻
    results_to_process = {}
    for source_id, source_titles in results.items():
        if source_id not in config.title_info:
            continue
        
        filtered_titles = {}
        for title, title_data in source_titles.items():
            if title in config.title_info[source_id]:
                info = config.title_info[source_id][title]
                if info.get("last_time") == latest_time:
                    filtered_titles[title] = title_data
        
        if filtered_titles:
            results_to_process[source_id] = filtered_titles
    
    if not config.quiet:
        total_count = sum(len(titles) for titles in results_to_process.values())
        print(f"当前榜单模式：最新时间 {latest_time}，筛选出 {total_count} 条当前榜单新闻")
    
    return results_to_process


def _initialize_word_stats(config: WordFrequencyConfig) -> Tuple[Dict, int]:
    """初始化词频统计字典"""
    word_stats = {}
    
    for group in config.word_groups:
        group_key = group["group_key"]
        word_stats[group_key] = {
            "count": 0,
            "titles": {}
        }
    
    return word_stats, 0


def _process_title_data(
    title: str,
    title_data: Dict,
    source_id: str,
    config: WordFrequencyConfig,
    all_news_are_new: bool
) -> Optional[Dict]:
    """处理单个标题数据"""
    source_ranks = title_data.get("ranks", [])
    source_url = title_data.get("url", "")
    source_mobile_url = title_data.get("mobileUrl", "")
    source_image_url = title_data.get("image_url", "")
    
    # 获取历史信息
    first_time = ""
    last_time = ""
    count_info = 1
    ranks = source_ranks if source_ranks else []
    url = source_url
    mobile_url = source_mobile_url
    image_url = source_image_url
    
    if config.title_info and source_id in config.title_info and title in config.title_info[source_id]:
        info = config.title_info[source_id][title]
        first_time = info.get("first_time", "")
        last_time = info.get("last_time", "")
        count_info = info.get("count", 1)
        if "ranks" in info and info["ranks"]:
            ranks = info["ranks"]
        url = info.get("url", source_url)
        mobile_url = info.get("mobileUrl", source_mobile_url)
        image_url = info.get("image_url", source_image_url)
    
    if not ranks:
        ranks = [RANKING.DEFAULT_RANK]
    
    # 判断是否为新增
    is_new = all_news_are_new
    if not is_new and config.new_titles and source_id in config.new_titles:
        is_new = title in config.new_titles[source_id]
    
    return {
        "title": title,
        "source_name": config.id_to_name.get(source_id, source_id),
        "first_time": first_time,
        "last_time": last_time,
        "time_display": format_time_display(first_time, last_time, config.convert_time_func),
        "count": count_info,
        "ranks": ranks,
        "rank_threshold": config.rank_threshold,
        "url": url,
        "mobileUrl": mobile_url,
        "image_url": image_url,
        "is_new": is_new,
    }


def _sort_and_format_stats(
    config: WordFrequencyConfig,
    word_stats: Dict,
    total_titles: int
) -> List[Dict]:
    """排序和格式化统计结果"""
    stats = []
    
    # 创建 group_key 到位置、最大数量、显示名称的映射
    group_key_to_position = {
        group["group_key"]: idx for idx, group in enumerate(config.word_groups)
    }
    group_key_to_max_count = {
        group["group_key"]: group.get("max_count", 0) for group in config.word_groups
    }
    group_key_to_display_name = {
        group["group_key"]: group.get("display_name") for group in config.word_groups
    }
    
    for group_key, data in word_stats.items():
        all_titles = []
        for source_id, title_list in data["titles"].items():
            all_titles.extend(title_list)
        
        # 按权重排序
        sorted_titles = sorted(
            all_titles,
            key=lambda x: (
                -calculate_news_weight(x, config.rank_threshold, config.weight_config),
                min(x["ranks"]) if x["ranks"] else 999,
                -x["count"],
            ),
        )
        
        # 应用最大显示数量限制
        group_max_count = group_key_to_max_count.get(group_key, 0)
        if group_max_count == 0:
            group_max_count = config.max_news_per_keyword
        
        if group_max_count > 0:
            sorted_titles = sorted_titles[:group_max_count]
        
        # 优先使用 display_name，否则使用 group_key
        display_word = group_key_to_display_name.get(group_key) or group_key
        
        stats.append({
            "word": display_word,
            "count": data["count"],
            "position": group_key_to_position.get(group_key, 999),
            "titles": sorted_titles,
            "percentage": round(data["count"] / total_titles * 100, 2) if total_titles > 0 else 0,
        })
    
    # 根据配置选择排序优先级
    if config.sort_by_position_first:
        stats.sort(key=lambda x: (x["position"], -x["count"]))
    else:
        stats.sort(key=lambda x: (-x["count"], x["position"]))
    
    return stats


def _print_summary(config: WordFrequencyConfig, total_input_news: int, matched_count: int, matched_new_count: int) -> None:
    """打印汇总信息"""
    if config.quiet:
        return
    
    if config.mode == "incremental":
        if config.is_first_today:
            filter_status = "全部显示" if len(config.word_groups) == 1 and config.word_groups[0]["group_key"] == "全部新闻" else "频率词匹配"
            print(f"增量模式：当天第一次爬取，{total_input_news} 条新闻中有 {matched_new_count} 条{filter_status}")
        elif config.new_titles:
            total_new_count = sum(len(titles) for titles in config.new_titles.values())
            filter_status = "全部显示" if len(config.word_groups) == 1 and config.word_groups[0]["group_key"] == "全部新闻" else "匹配频率词"
            print(f"增量模式：{total_new_count} 条新增新闻中，有 {matched_new_count} 条{filter_status}")
            if matched_new_count == 0 and len(config.word_groups) > 1:
                print("增量模式：没有新增新闻匹配频率词，将不会发送通知")
        else:
            print("增量模式：未检测到新增新闻")
    
    elif config.mode == "current":
        if config.is_first_today:
            filter_status = "全部显示" if len(config.word_groups) == 1 and config.word_groups[0]["group_key"] == "全部新闻" else "频率词匹配"
            print(f"当前榜单模式：当天第一次爬取，{total_input_news} 条当前榜单新闻中有 {matched_new_count} 条{filter_status}")
        else:
            filter_status = "全部显示" if len(config.word_groups) == 1 and config.word_groups[0]["group_key"] == "全部新闻" else "频率词匹配"
            print(f"当前榜单模式：{total_input_news} 条当前榜单新闻中有 {matched_count} 条{filter_status}")
    
    elif config.mode == "daily":
        print(f"当日汇总模式：处理 {total_input_news} 条新闻，模式：频率词过滤")
        print(f"频率词过滤后：{matched_count} 条新闻匹配")


def format_time_display(
    first_time: str,
    last_time: str,
    convert_time_func: Callable[[str], str],
) -> str:
    """
    格式化时间显示（将 HH-MM 转换为 HH:MM）

    Args:
        first_time: 首次出现时间
        last_time: 最后出现时间
        convert_time_func: 时间格式转换函数

    Returns:
        str: 格式化后的时间显示字符串
    """
    if not first_time:
        return ""
    # 转换为显示格式
    first_display = convert_time_func(first_time)
    last_display = convert_time_func(last_time)
    if first_display == last_display or not last_display:
        return first_display
    else:
        return f"[{first_display} ~ {last_display}]"


def count_word_frequency(
    results: Dict,
    word_groups: List[Dict],
    filter_words: List[str],
    id_to_name: Dict,
    title_info: Optional[Dict] = None,
    rank_threshold: int = 3,
    new_titles: Optional[Dict] = None,
    mode: str = "daily",
    global_filters: Optional[List[str]] = None,
    weight_config: Optional[Dict] = None,
    max_news_per_keyword: int = 0,
    sort_by_position_first: bool = False,
    is_first_crawl_func: Optional[Callable[[], bool]] = None,
    convert_time_func: Optional[Callable[[str], str]] = None,
    quiet: bool = False,
) -> Tuple[List[Dict], int]:
    """
    统计词频，支持必须词、频率词、过滤词、全局过滤词，并标记新增标题

    Args:
        results: 抓取结果 {source_id: {title: title_data}}
        word_groups: 词组配置列表
        filter_words: 过滤词列表
        id_to_name: ID 到名称的映射
        title_info: 标题统计信息（可选）
        rank_threshold: 排名阈值
        new_titles: 新增标题（可选）
        mode: 报告模式 (daily/incremental/current)
        global_filters: 全局过滤词（可选）
        weight_config: 权重配置
        max_news_per_keyword: 每个关键词最大显示数量
        sort_by_position_first: 是否优先按配置位置排序
        is_first_crawl_func: 检测是否是当天第一次爬取的函数
        convert_time_func: 时间格式转换函数
        quiet: 是否静默模式（不打印日志）

    Returns:
        Tuple[List[Dict], int]: (统计结果列表, 总标题数)
    """
    # 1. 构建配置对象
    config = WordFrequencyConfig(
        word_groups=word_groups if word_groups else [{"required": [], "normal": [], "group_key": "全部新闻"}],
        filter_words=filter_words if word_groups else [],
        id_to_name=id_to_name,
        title_info=title_info,
        rank_threshold=rank_threshold,
        new_titles=new_titles,
        mode=mode,
        global_filters=global_filters,
        weight_config=weight_config,
        max_news_per_keyword=max_news_per_keyword,
        sort_by_position_first=sort_by_position_first,
        is_first_crawl_func=is_first_crawl_func,
        convert_time_func=convert_time_func,
        quiet=quiet,
    )
    
    if not word_groups:
        if not quiet:
            print("频率词配置为空，将显示所有新闻")

    # 2. 确定处理范围
    results_to_process, all_news_are_new = _determine_processing_scope(config, results)
    
    # 打印初始状态日志 (Daily Only)
    if mode == "daily":
        total_input_news = sum(len(titles) for titles in results.values())
        filter_status = "全部显示" if len(config.word_groups) == 1 and config.word_groups[0]["group_key"] == "全部新闻" else "频率词过滤"
        if not quiet:
            print(f"当日汇总模式：处理 {total_input_news} 条新闻，模式：{filter_status}")

    # 3. 初始化统计结构
    word_stats, total_titles = _initialize_word_stats(config)
    processed_titles = {}
    matched_new_count = 0
    matched_count = 0

    # 4. 遍历处理数据
    for source_id, titles_data in results_to_process.items():
        total_titles += len(titles_data)
        
        for title, title_data in titles_data.items():
            # 去重检查 (同一 source_id 下)
            if source_id in processed_titles and title in processed_titles[source_id]:
                continue

            # 匹配检查
            if not matches_word_groups(title, config.word_groups, config.filter_words, config.global_filters):
                continue
            
            matched_count += 1
            
            # 统计新增数
            if (mode == "incremental" and all_news_are_new) or (mode == "current" and config.is_first_today):
                matched_new_count += 1
                
            # 处理单条数据
            processed_data = _process_title_data(title, title_data, source_id, config, all_news_are_new)
            
            # 由于上面已经检查了 matches_word_groups，这里我们需要找到具体匹配归属的 group
            # 为了复用逻辑并准确归类，这里重新遍历 word_groups 查找归属
            title_lower = str(title).lower()
            for group in config.word_groups:
                # 再次匹配确认归属 (处理 "全部新闻" 特例 或 正常匹配)
                is_match = False
                if len(config.word_groups) == 1 and config.word_groups[0]["group_key"] == "全部新闻":
                    is_match = True
                else:
                    req_match = not group["required"] or all(_word_matches(w, title_lower) for w in group["required"])
                    norm_match = not group["normal"] or any(_word_matches(w, title_lower) for w in group["normal"])
                    # 如果有 required 但不满足 -> False
                    # 如果没有 required，须满足 normal (如果有 normal) -> True
                    # 如果 required 和 normal 都没有 -> (逻辑上应该在 matches_word_groups 处理过，这里简化)
                    if group["required"] and not req_match:
                        continue
                    if group["normal"] and not norm_match and not (not group["required"] and not group["normal"]):
                         continue
                    is_match = True
                
                if is_match:
                    group_key = group["group_key"]
                    word_stats[group_key]["count"] += 1
                    if source_id not in word_stats[group_key]["titles"]:
                        word_stats[group_key]["titles"][source_id] = []
                    
                    word_stats[group_key]["titles"][source_id].append(processed_data)
                    
                    # 记录已处理
                    if source_id not in processed_titles:
                        processed_titles[source_id] = {}
                    processed_titles[source_id][title] = True
                    break

    # 5. 打印汇总信息
    # 计算 total_input_news 用于日志 (Daily 已打印，这里主要针对 Incremental/Current)
    total_input_news = sum(len(titles) for titles in results.values()) if mode != "daily" else total_titles
    # 修正 matched_count 对于非 daily 模式的含义
    final_matched_count = matched_count
    
    _print_summary(config, total_input_news, final_matched_count, matched_new_count)

    # 6. 格式化输出
    stats = _sort_and_format_stats(config, word_stats, total_titles)
    
    return stats, total_titles



def count_rss_frequency(
    rss_items: List[Dict],
    word_groups: List[Dict],
    filter_words: List[str],
    global_filters: Optional[List[str]] = None,
    new_items: Optional[List[Dict]] = None,
    max_news_per_keyword: int = 0,
    sort_by_position_first: bool = False,
    timezone: str = "Asia/Shanghai",
    rank_threshold: int = 5,
    quiet: bool = False,
) -> Tuple[List[Dict], int]:
    """
    按关键词分组统计 RSS 条目（与热榜统计格式一致）

    Args:
        rss_items: RSS 条目列表，每个条目包含：
            - title: 标题
            - feed_id: RSS 源 ID
            - feed_name: RSS 源名称
            - url: 文章链接
            - published_at: 发布时间（ISO 格式）
        word_groups: 词组配置列表
        filter_words: 过滤词列表
        global_filters: 全局过滤词（可选）
        new_items: 新增条目列表（可选，用于标记 is_new）
        max_news_per_keyword: 每个关键词最大显示数量
        sort_by_position_first: 是否优先按配置位置排序
        timezone: 时区名称（用于时间格式化）
        quiet: 是否静默模式

    Returns:
        Tuple[List[Dict], int]: (统计结果列表, 总条目数)
        统计结果格式与热榜一致：
        [
            {
                "word": "关键词",
                "count": 5,
                "position": 0,
                "titles": [
                    {
                        "title": "标题",
                        "source_name": "Hacker News",
                        "time_display": "12-29 08:20",
                        "count": 1,
                        "ranks": [1],  # RSS 用发布时间顺序作为排名
                        "rank_threshold": 50,
                        "url": "...",
                        "mobile_url": "",
                        "is_new": True/False
                    }
                ],
                "percentage": 10.0
            }
        ]
    """
    from trendradar.utils.time import format_iso_time_friendly

    if not rss_items:
        return [], 0

    # 如果没有配置词组，创建一个包含所有条目的虚拟词组
    if not word_groups:
        if not quiet:
            print("[RSS] 频率词配置为空，将显示所有 RSS 条目")
        word_groups = [{"required": [], "normal": [], "group_key": "全部 RSS"}]
        filter_words = []

    # 创建新增条目的 URL 集合，用于快速查找
    new_urls = set()
    if new_items:
        for item in new_items:
            if item.get("url"):
                new_urls.add(item["url"])

    # 初始化词组统计
    word_stats = {}
    for group in word_groups:
        group_key = group["group_key"]
        word_stats[group_key] = {"count": 0, "titles": []}

    total_items = len(rss_items)
    processed_urls = set()  # 用于去重

    # 为每个条目分配一个基于发布时间的"排名"
    # 按发布时间排序，最新的排在前面
    sorted_items = sorted(
        rss_items,
        key=lambda x: x.get("published_at", ""),
        reverse=True
    )
    url_to_rank = {item.get("url", ""): idx + 1 for idx, item in enumerate(sorted_items)}

    for item in rss_items:
        title = item.get("title", "")
        url = item.get("url", "")

        # 去重
        if url and url in processed_urls:
            continue
        if url:
            processed_urls.add(url)

        # 使用统一的匹配逻辑
        if not matches_word_groups(title, word_groups, filter_words, global_filters):
            continue

        # 找到匹配的词组
        title_lower = title.lower()
        for group in word_groups:
            required_words = group["required"]
            normal_words = group["normal"]
            group_key = group["group_key"]

            # "全部 RSS" 模式：所有条目都匹配
            if len(word_groups) == 1 and word_groups[0]["group_key"] == "全部 RSS":
                matched = True
            else:
                # 检查必须词（支持正则语法）
                if required_words:
                    all_required_present = all(
                        _word_matches(req_item, title_lower)
                        for req_item in required_words
                    )
                    if not all_required_present:
                        continue

                # 检查普通词（支持正则语法）
                if normal_words:
                    any_normal_present = any(
                        _word_matches(normal_item, title_lower)
                        for normal_item in normal_words
                    )
                    if not any_normal_present:
                        continue

                matched = True

            if matched:
                word_stats[group_key]["count"] += 1

                # 格式化时间显示
                published_at = item.get("published_at", "")
                time_display = format_iso_time_friendly(published_at, timezone, include_date=True) if published_at else ""

                # 判断是否为新增
                is_new = url in new_urls if url else False

                # 获取排名（基于发布时间顺序）
                rank = url_to_rank.get(url, 99) if url else 99

                title_data = {
                    "title": title,
                    "source_name": item.get("feed_name", item.get("feed_id", "RSS")),
                    "time_display": time_display,
                    "count": 1,  # RSS 条目通常只出现一次
                    "ranks": [rank],
                    "rank_threshold": rank_threshold,
                    "url": url,
                    "mobile_url": "",
                    "image_url": item.get("image_url", ""),
                    "is_new": is_new,
                }
                word_stats[group_key]["titles"].append(title_data)
                break  # 一个条目只匹配第一个词组

    # 构建统计结果
    stats = []
    group_key_to_position = {
        group["group_key"]: idx for idx, group in enumerate(word_groups)
    }
    group_key_to_max_count = {
        group["group_key"]: group.get("max_count", 0) for group in word_groups
    }
    group_key_to_display_name = {
        group["group_key"]: group.get("display_name") for group in word_groups
    }

    for group_key, data in word_stats.items():
        if data["count"] == 0:
            continue

        # 按发布时间排序（最新在前）
        sorted_titles = sorted(
            data["titles"],
            key=lambda x: x["ranks"][0] if x["ranks"] else 999
        )

        # 应用最大显示数量限制
        group_max_count = group_key_to_max_count.get(group_key, 0)
        if group_max_count == 0:
            group_max_count = max_news_per_keyword
        if group_max_count > 0:
            sorted_titles = sorted_titles[:group_max_count]

        # 优先使用 display_name，否则使用 group_key
        display_word = group_key_to_display_name.get(group_key) or group_key

        stats.append({
            "word": display_word,
            "count": data["count"],
            "position": group_key_to_position.get(group_key, 999),
            "titles": sorted_titles,
            "percentage": round(data["count"] / total_items * 100, 2) if total_items > 0 else 0,
        })

    # 排序
    if sort_by_position_first:
        stats.sort(key=lambda x: (x["position"], -x["count"]))
    else:
        stats.sort(key=lambda x: (-x["count"], x["position"]))

    matched_count = sum(stat["count"] for stat in stats)
    if not quiet:
        print(f"[RSS] 关键词分组统计：{matched_count}/{total_items} 条匹配")

    return stats, total_items


def convert_keyword_stats_to_platform_stats(
    keyword_stats: List[Dict],
    weight_config: Dict,
    rank_threshold: int = 5,
) -> List[Dict]:
    """
    将按关键词分组的统计数据转换为按平台分组的统计数据

    Args:
        keyword_stats: 原始按关键词分组的统计数据
        weight_config: 权重配置
        rank_threshold: 排名阈值

    Returns:
        按平台分组的统计数据，格式与原 stats 一致
    """
    # 1. 收集所有新闻，按平台分组
    platform_map: Dict[str, List[Dict]] = {}

    for stat in keyword_stats:
        keyword = stat["word"]
        for title_data in stat["titles"]:
            source_name = title_data["source_name"]

            if source_name not in platform_map:
                platform_map[source_name] = []

            # 复制 title_data 并添加匹配的关键词
            title_with_keyword = title_data.copy()
            title_with_keyword["matched_keyword"] = keyword
            platform_map[source_name].append(title_with_keyword)

    # 2. 去重（同一平台下相同标题只保留一条，保留第一个匹配的关键词）
    for source_name, titles in platform_map.items():
        seen_titles: Dict[str, bool] = {}
        unique_titles = []
        for title_data in titles:
            title_text = title_data["title"]
            if title_text not in seen_titles:
                seen_titles[title_text] = True
                unique_titles.append(title_data)
        platform_map[source_name] = unique_titles

    # 3. 按权重排序每个平台内的新闻
    for source_name, titles in platform_map.items():
        platform_map[source_name] = sorted(
            titles,
            key=lambda x: (
                -calculate_news_weight(x, rank_threshold, weight_config),
                min(x["ranks"]) if x["ranks"] else 999,
                -x["count"],
            ),
        )

    # 4. 构建平台统计结果
    platform_stats = []
    for source_name, titles in platform_map.items():
        platform_stats.append({
            "word": source_name,  # 平台名作为分组标识
            "count": len(titles),
            "titles": titles,
            "percentage": 0,  # 可后续计算
        })

    # 5. 按新闻条数排序平台
    platform_stats.sort(key=lambda x: -x["count"])

    return platform_stats
