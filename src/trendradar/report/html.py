# coding=utf-8
"""
HTML 报告渲染模块

提供 HTML 格式的热点新闻报告生成功能
"""

from datetime import datetime
from typing import Dict, List, Optional, Callable

from trendradar.report.helpers import html_escape


def render_html_content(
    report_data: Dict,
    total_titles: int,
    is_daily_summary: bool = False,
    mode: str = "daily",
    update_info: Optional[Dict] = None,
    *,
    reverse_content_order: bool = False,
    get_time_func: Optional[Callable[[], datetime]] = None,
    rss_items: Optional[List[Dict]] = None,
    rss_new_items: Optional[List[Dict]] = None,
    display_mode: str = "keyword",
    report_title: str = "热点新闻分析",
) -> str:
    """渲染HTML内容

    Args:
        report_data: 报告数据字典，包含 stats, new_titles, failed_ids, total_new_count
        total_titles: 新闻总数
        is_daily_summary: 是否为当日汇总
        mode: 报告模式 ("daily", "current", "incremental")
        update_info: 更新信息（可选）
        reverse_content_order: 是否反转内容顺序（新增热点在前）
        get_time_func: 获取当前时间的函数（可选，默认使用 datetime.now）
        rss_items: RSS 统计条目列表（可选）
        rss_new_items: RSS 新增条目列表（可选）
        display_mode: 显示模式 ("keyword"=按关键词分组, "platform"=按平台分组)

    Returns:
        渲染后的 HTML 字符串
    """
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>""" + report_title + """</title>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js" integrity="sha512-BNaRQnYJYiPSqHHDb58B0yaPfCu+Wgds8Gp/gU33kqBtgNS4tSPHuGibyoeqMV/TJlSKda6FXzoEyYGjTe+vXA==" crossorigin="anonymous" referrerpolicy="no-referrer"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

            * { box-sizing: border-box; }
            body {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
                margin: 0;
                padding: 24px 16px;
                background-color: #f3f4f6;
                color: #1f2937;
                line-height: 1.6;
            }

            .container {
                max-width: 640px;
                margin: 0 auto;
                background: transparent;
            }

            .header {
                background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
                color: white;
                padding: 48px 32px;
                text-align: center;
                position: relative;
                border-radius: 20px 20px 0 0;
                box-shadow: 0 4px 20px -5px rgba(99, 102, 241, 0.4);
            }

            .save-buttons {
                position: absolute;
                top: 16px;
                right: 16px;
                display: flex;
                gap: 8px;
            }

            .save-btn {
                background: rgba(255, 255, 255, 0.15);
                border: 1px solid rgba(255, 255, 255, 0.2);
                color: white;
                padding: 6px 12px;
                border-radius: 8px;
                cursor: pointer;
                font-size: 12px;
                font-weight: 500;
                transition: all 0.2s ease;
                backdrop-filter: blur(8px);
                white-space: nowrap;
            }

            .save-btn:hover {
                background: rgba(255, 255, 255, 0.25);
                transform: translateY(-1px);
            }

            .header-title {
                font-size: 26px;
                font-weight: 800;
                margin: 0 0 28px 0;
                letter-spacing: -0.02em;
                text-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }

            .header-info {
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 12px;
                background: rgba(255, 255, 255, 0.1);
                backdrop-filter: blur(12px);
                padding: 16px;
                border-radius: 16px;
                border: 1px solid rgba(255, 255, 255, 0.2);
            }

            .info-item {
                text-align: center;
            }

            .info-label {
                display: block;
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                opacity: 0.8;
                margin-bottom: 4px;
                font-weight: 600;
            }

            .info-value {
                font-weight: 700;
                font-size: 15px;
            }

            .content {
                padding: 0;
                margin-top: 24px;
                position: relative;
                z-index: 10;
            }

            .word-group {
                margin-bottom: 32px;
            }

            .section-label {
                padding: 0 16px;
                margin-bottom: 16px;
                font-weight: 700;
                font-size: 14px;
                color: #6b7280;
                display: flex;
                align-items: center;
                gap: 8px;
            }

            .section-label::before {
                content: "";
                display: block;
                width: 4px;
                height: 16px;
                background: #6366f1;
                border-radius: 2px;
            }

            .word-header {
                background: white;
                margin: 0 0 12px 0;
                padding: 16px 20px;
                border-radius: 16px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
            }

            .word-name {
                font-size: 18px;
                font-weight: 700;
                color: #111827;
                background: linear-gradient(to right, #111827, #6b7280);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }

            .word-count-badge {
                background: #f3f4f6;
                color: #4b5563;
                padding: 4px 10px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 600;
            }

            .word-count-badge.hot { background: #fee2e2; color: #dc2626; }
            .word-count-badge.warm { background: #ffedd5; color: #ea580c; }

            .news-card {
                background: white;
                margin-bottom: 12px;
                padding: 20px;
                border-radius: 16px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.05);
                transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
                display: flex;
                gap: 16px;
                text-decoration: none;
                color: inherit;
                position: relative;
                border: 1px solid transparent;
            }

            .news-card:hover {
                transform: translateY(-3px);
                box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
                border-color: #e5e7eb;
            }

            .news-card.new::before {
                content: "NEW";
                position: absolute;
                top: -8px;
                right: 20px;
                background: #facc15;
                color: #854d0e;
                font-size: 10px;
                font-weight: 800;
                padding: 2px 8px;
                border-radius: 6px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }

            .news-rank-circle {
                width: 38px;
                height: 38px;
                border-radius: 12px;
                background: #f8fafc;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 14px;
                font-weight: 700;
                color: #64748b;
                flex-shrink: 0;
            }

            .news-rank-circle.top { background: #ef4444; color: white; }
            .news-rank-circle.high { background: #f97316; color: white; }

            .news-body {
                flex: 1;
                min-width: 0;
            }

            .news-tags {
                display: flex;
                gap: 6px;
                margin-bottom: 8px;
                flex-wrap: wrap;
            }

            .badge {
                font-size: 11px;
                font-weight: 600;
                padding: 2px 8px;
                border-radius: 6px;
            }

            .badge-source { background: #f1f5f9; color: #475569; }
            .badge-keyword { background: #eef2ff; color: #4f46e5; }
            .badge-time { background: #f8fafc; color: #94a3b8; font-weight: 400; }
            .badge-count { background: #ecfdf5; color: #059669; }

            .news-title-text {
                font-size: 16px;
                font-weight: 600;
                color: #111827;
                line-height: 1.5;
                margin: 0;
                display: block;
            }

            .news-card:hover .news-title-text {
                color: #4f46e5;
            }

            .rss-section {
                padding: 0 16px;
                margin-top: 40px;
            }

            .rss-card {
                background: #f0fdf4;
                border: 1px solid #dcfce7;
                border-radius: 16px;
                padding: 16px;
                margin-bottom: 12px;
                display: block;
                text-decoration: none;
                color: inherit;
                transition: all 0.2s ease;
            }

            .rss-card:hover {
                background: #dcfce7;
                transform: translateX(4px);
            }

            .rss-meta {
                display: flex;
                gap: 8px;
                margin-bottom: 8px;
                font-size: 11px;
                font-weight: 600;
                color: #059669;
            }

            .rss-title {
                font-size: 14px;
                font-weight: 600;
                color: #065f46;
                margin-bottom: 6px;
            }

            .rss-summary {
                font-size: 13px;
                color: #374151;
                opacity: 0.8;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
                overflow: hidden;
            }

            .new-section {
                margin-top: 48px;
                padding: 0 16px;
            }

            .source-group {
                margin-bottom: 24px;
            }

            .source-title {
                font-size: 13px;
                font-weight: 600;
                color: #94a3b8;
                margin-bottom: 12px;
                display: flex;
                align-items: center;
                gap: 8px;
            }

            .incremental-item {
                background: white;
                padding: 12px 16px;
                border-radius: 12px;
                margin-bottom: 8px;
                font-size: 14px;
                border: 1px solid #f1f5f9;
                display: flex;
                align-items: center;
                gap: 12px;
            }

            .inc-rank {
                font-size: 11px;
                font-weight: 800;
                color: #94a3b8;
                width: 20px;
                text-align: center;
            }

            .error-card {
                background: #fff1f2;
                border: 1px solid #fecdd3;
                padding: 16px;
                border-radius: 12px;
                margin: 0 16px 24px 16px;
            }

            .error-msg {
                color: #be123c;
                font-size: 13px;
                margin: 4px 0;
                font-family: monospace;
            }

            .footer {
                margin-top: 64px;
                padding: 40px 24px;
                background: white;
                border-radius: 32px 32px 0 0;
                text-align: center;
                box-shadow: 0 -4px 6px -1px rgba(0, 0, 0, 0.05);
            }

            .footer-content { font-size: 13px; color: #64748b; }
            .project-badge {
                display: inline-block;
                padding: 4px 12px;
                background: #f1f5f9;
                border-radius: 8px;
                font-weight: 700;
                color: #1e293b;
                margin-bottom: 12px;
            }

            @media (max-width: 480px) {
                .header-info { grid-template-columns: 1fr 1fr; }
                .news-card { padding: 16px; gap: 12px; }
                .news-rank-circle { width: 32px; height: 32px; font-size: 12px; border-radius: 10px; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="save-buttons">
                    <button class="save-btn" onclick="saveAsImage()">保存为图片</button>
                    <button class="save-btn" onclick="saveAsMultipleImages()">分段保存</button>
                </div>
                <div class="header-title">""" + report_title + """</div>
                <div class="header-info">
                    <div class="info-item">
                        <span class="info-label">报告类型</span>
                        <span class="info-value">"""

    # 处理报告类型显示
    if is_daily_summary:
        if mode == "current":
            html += "当前榜单"
        elif mode == "incremental":
            html += "增量模式"
        else:
            html += "当日汇总"
    else:
        html += "实时分析"

    html += """</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">新闻总数</span>
                        <span class="info-value">"""

    html += f"{total_titles} 条"

    # 计算筛选后的热点新闻数量
    hot_news_count = sum(len(stat["titles"]) for stat in report_data["stats"])

    html += """</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">热点新闻</span>
                        <span class="info-value">"""

    html += f"{hot_news_count} 条"

    html += """</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">生成时间</span>
                        <span class="info-value">"""

    # 使用提供的时间函数或默认 datetime.now
    if get_time_func:
        now = get_time_func()
    else:
        now = datetime.now()
    html += now.strftime("%m-%d %H:%M")

    html += """</span>
                    </div>
                </div>
            </div>

            <div class="content">"""

    # 处理失败ID错误信息
    if report_data["failed_ids"]:
        html += """
                <div class="error-card">
                    <div style="font-weight: 700; color: #e11d48; font-size: 14px; margin-bottom: 8px;">⚠️ 以下平台抓取失败</div>"""
        for id_value in report_data["failed_ids"]:
            html += f'<div class="error-msg">• {html_escape(id_value)}</div>'
        html += """
                </div>"""

    # 生成热点词汇统计部分的HTML
    stats_html = ""
    if report_data["stats"]:
        stats_html += '<div class="section-label">热点聚焦</div>'
        total_count = len(report_data["stats"])

        for i, stat in enumerate(report_data["stats"], 1):
            count = stat["count"]

            # 确定热度等级
            if count >= 10:
                count_class = "hot"
            elif count >= 5:
                count_class = "warm"
            else:
                count_class = ""

            escaped_word = html_escape(stat["word"])

            stats_html += f"""
                <div class="word-group">

                    <div class="word-header">
                        <div class="word-name">{escaped_word}</div>
                        <div class="word-index">{i}/{total_count}</div>
                        <div class="word-count-badge {count_class}">{count} 条热议</div>
                    </div>"""

            # 处理每个词组下的新闻标题
            for j, title_data in enumerate(stat["titles"], 1):
                is_new = title_data.get("is_new", False)
                new_class = "new" if is_new else ""
                
                # 提取链接
                link_url = title_data.get("mobile_url") or title_data.get("url", "")
                escaped_url = html_escape(link_url) if link_url else "#"

                # 处理排名
                rank_html = ""
                ranks = title_data.get("ranks", [])
                if ranks:
                    min_rank = min(ranks)
                    max_rank = max(ranks)
                    rank_threshold = title_data.get("rank_threshold", 10)
                    rank_class = "top" if min_rank <= 3 else ("high" if min_rank <= rank_threshold else "")
                    rank_text = str(min_rank) if min_rank == max_rank else f"{min_rank}"
                    rank_html = f'<div class="news-rank-circle {rank_class}">{rank_text}</div>'
                else:
                    rank_html = f'<div class="news-rank-circle">{j}</div>'

                stats_html += f"""
                    <a href="{escaped_url}" target="_blank" class="news-card {new_class}">
                        {rank_html}
                        <div class="news-body">
                            <div class="news-tags">"""

                # 来源标签
                stats_html += f'<span class="badge badge-source">{html_escape(title_data["source_name"])}</span>'
                
                # 关键词标签（platform模式下）
                if display_mode != "keyword":
                    matched_keyword = title_data.get("matched_keyword", "")
                    if matched_keyword:
                        stats_html += f'<span class="badge badge-keyword">{html_escape(matched_keyword)}</span>'

                # 时间标签
                time_display = title_data.get("time_display", "")
                if time_display:
                    simplified_time = time_display.replace(" ~ ", "~").replace("[", "").replace("]", "")
                    stats_html += f'<span class="badge badge-time">{html_escape(simplified_time)}</span>'
                
                # 出现次数
                count_info = title_data.get("count", 1)
                if count_info > 1:
                    stats_html += f'<span class="badge badge-count">{count_info}次出现</span>'

                stats_html += f"""
                            </div>
                            <h3 class="news-title-text">{html_escape(title_data["title"])}</h3>
                        </div>
                    </a>"""

            stats_html += """
                </div>"""

    # 生成新增热点区域的HTML
    new_titles_html = ""
    if report_data["new_titles"]:
        new_titles_html += f"""
                <div class="new-section">
                    <div class="section-label">新增热点</div>
                    <div class="word-header" style="margin-bottom: 24px;">
                        <div class="word-name">本次发现 {report_data['total_new_count']} 条新动态</div>
                    </div>"""

        for source_data in report_data["new_titles"]:
            escaped_source = html_escape(source_data["source_name"])
            titles_count = len(source_data["titles"])

            new_titles_html += f"""
                    <div class="source-group">
                        <div class="source-title">
                            <span style="width: 8px; height: 8px; background: #94a3b8; border-radius: 50%; display: inline-block;"></span>
                            {escaped_source} · {titles_count}条
                        </div>"""

            for idx, title_data in enumerate(source_data["titles"], 1):
                ranks = title_data.get("ranks", [])
                rank_class = ""
                if ranks:
                    min_rank = min(ranks)
                    rank_class = "top" if min_rank <= 3 else ("high" if min_rank <= title_data.get("rank_threshold", 10) else "")
                    rank_text = str(min_rank)
                else:
                    rank_text = "•"

                link_url = title_data.get("mobile_url") or title_data.get("url", "")
                escaped_url = html_escape(link_url) if link_url else "#"

                new_titles_html += f"""
                        <a href="{escaped_url}" target="_blank" class="incremental-item" style="text-decoration: none; color: inherit;">
                            <div class="inc-rank">{rank_text}</div>
                            <div style="flex: 1; min-width: 0; font-weight: 500; color: #374151;">{html_escape(title_data["title"])}</div>
                        </a>"""

            new_titles_html += """
                    </div>"""

        new_titles_html += """
                </div>"""

    # 生成 RSS 统计内容
    def render_rss_stats_html(stats: List[Dict], title: str = "RSS 订阅更新") -> str:
        """渲染 RSS 统计区块 HTML

        Args:
            stats: RSS 分组统计列表，格式与热榜一致：
                [
                    {
                        "word": "关键词",
                        "count": 5,
                        "titles": [
                            {
                                "title": "标题",
                                "source_name": "Feed 名称",
                                "time_display": "12-29 08:20",
                                "url": "...",
                                "is_new": True/False
                            }
                        ]
                    }
                ]
            title: 区块标题

        Returns:
            渲染后的 HTML 字符串
        """
        if not stats:
            return ""

        # 计算总条目数
        total_count = sum(stat.get("count", 0) for stat in stats)
        if total_count == 0:
            return ""

        rss_html = f"""
                <div class="rss-section">
                    <div class="section-label">{title}</div>
                    <div class="word-header" style="margin-bottom: 24px;">
                        <div class="word-name">集成订阅源 (共 {total_count} 条)</div>
                    </div>"""

        for stat in stats:
            keyword = stat.get("word", "")
            titles = stat.get("titles", [])
            if not titles:
                continue

            for title_data in titles:
                is_new = title_data.get("is_new", False)
                url = title_data.get("url", "")
                escaped_url = html_escape(url) if url else "#"

                rss_html += f"""
                    <a href="{escaped_url}" target="_blank" class="rss-card">
                        <div class="rss-meta">"""

                if title_data.get("source_name"):
                    rss_html += f'<span class="badge badge-source">{html_escape(title_data["source_name"])}</span>'
                
                if title_data.get("time_display"):
                    rss_html += f'<span class="badge badge-time">{html_escape(title_data["time_display"])}</span>'

                if is_new:
                    rss_html += '<span class="badge" style="background: #facc15; color: #854d0e;">NEW</span>'

                rss_html += f"""
                        </div>
                        <div class="rss-title">{html_escape(title_data.get("title", ""))}</div>
                    </a>"""

        rss_html += """
                </div>"""
        return rss_html
        return rss_html

    # 生成 RSS 统计和新增 HTML
    rss_stats_html = render_rss_stats_html(rss_items, "RSS 订阅更新") if rss_items else ""
    rss_new_html = render_rss_stats_html(rss_new_items, "RSS 新增更新") if rss_new_items else ""

    # 根据配置决定内容顺序（与推送逻辑一致）
    if reverse_content_order:
        # 新增在前，统计在后
        # 顺序：热榜新增 → RSS新增 → 热榜统计 → RSS统计
        html += new_titles_html + rss_new_html + stats_html + rss_stats_html
    else:
        # 默认：统计在前，新增在后
        # 顺序：热榜统计 → RSS统计 → 热榜新增 → RSS新增
        html += stats_html + rss_stats_html + new_titles_html + rss_new_html

    html += """
            </div>

            <div class="footer">
                <div class="project-badge">TrendRadar</div>
                <div class="footer-content">
                    专业的新闻热点追踪与分析平台 · 
                    <a href="https://github.com/MisonL/TrendRadar" target="_blank" class="footer-link">
                        GitHub Open Source
                    </a>"""

    if update_info:
        html += f"""
                    <br>
                    <span style="color: #ea580c; font-weight: 500;">
                        发现新版本 {update_info['remote_version']}，当前版本 {update_info['current_version']}
                    </span>"""

    html += """
                </div>
            </div>
        </div>

        <script>
            async function saveAsImage() {
                const button = event.target;
                const originalText = button.textContent;

                try {
                    button.textContent = '生成中...';
                    button.disabled = true;
                    window.scrollTo(0, 0);

                    // 等待页面稳定
                    await new Promise(resolve => setTimeout(resolve, 200));

                    // 截图前隐藏按钮
                    const buttons = document.querySelector('.save-buttons');
                    buttons.style.visibility = 'hidden';

                    // 再次等待确保按钮完全隐藏
                    await new Promise(resolve => setTimeout(resolve, 100));

                    const container = document.querySelector('.container');

                    const canvas = await html2canvas(container, {
                        backgroundColor: '#ffffff',
                        scale: 1.5,
                        useCORS: true,
                        allowTaint: false,
                        imageTimeout: 10000,
                        removeContainer: false,
                        foreignObjectRendering: false,
                        logging: false,
                        width: container.offsetWidth,
                        height: container.offsetHeight,
                        x: 0,
                        y: 0,
                        scrollX: 0,
                        scrollY: 0,
                        windowWidth: window.innerWidth,
                        windowHeight: window.innerHeight
                    });

                    buttons.style.visibility = 'visible';

                    const link = document.createElement('a');
                    const now = new Date();
                    const filename = `TrendRadar_热点新闻分析_${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}.png`;

                    link.download = filename;
                    link.href = canvas.toDataURL('image/png', 1.0);

                    // 触发下载
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);

                    button.textContent = '保存成功!';
                    setTimeout(() => {
                        button.textContent = originalText;
                        button.disabled = false;
                    }, 2000);

                } catch (error) {
                    const buttons = document.querySelector('.save-buttons');
                    buttons.style.visibility = 'visible';
                    button.textContent = '保存失败';
                    setTimeout(() => {
                        button.textContent = originalText;
                        button.disabled = false;
                    }, 2000);
                }
            }

            async function saveAsMultipleImages() {
                const button = event.target;
                const originalText = button.textContent;
                const container = document.querySelector('.container');
                const scale = 1.5;
                const maxHeight = 5000 / scale;

                try {
                    button.textContent = '分析中...';
                    button.disabled = true;

                    // 获取所有可能的分割元素
                    const newsItems = Array.from(container.querySelectorAll('.news-card'));
                    const wordGroups = Array.from(container.querySelectorAll('.word-group'));
                    const newSection = container.querySelector('.new-section');
                    const errorCard = container.querySelector('.error-card');
                    const header = container.querySelector('.header');
                    const footer = container.querySelector('.footer');

                    // 计算元素位置和高度
                    const containerRect = container.getBoundingClientRect();
                    const elements = [];

                    // 添加header作为必须包含的元素
                    elements.push({
                        type: 'header',
                        element: header,
                        top: 0,
                        bottom: header.offsetHeight,
                        height: header.offsetHeight
                    });

                    // 添加错误信息（如果存在）
                    if (errorCard) {
                        const rect = errorCard.getBoundingClientRect();
                        elements.push({
                            type: 'error',
                            element: errorCard,
                            top: rect.top - containerRect.top,
                            bottom: rect.bottom - containerRect.top,
                            height: rect.height
                        });
                    }

                    // 按word-group分组处理news-card
                    wordGroups.forEach(group => {
                        const groupRect = group.getBoundingClientRect();
                        const groupNewsItems = group.querySelectorAll('.news-card');

                        // 添加word-group的header部分
                        const wordHeader = group.querySelector('.word-header');
                        if (wordHeader) {
                            const headerRect = wordHeader.getBoundingClientRect();
                            elements.push({
                                type: 'word-header',
                                element: wordHeader,
                                parent: group,
                                top: groupRect.top - containerRect.top,
                                bottom: headerRect.bottom - containerRect.top,
                                height: headerRect.height
                            });
                        }

                        // 添加每个news-card
                        groupNewsItems.forEach(item => {
                            const rect = item.getBoundingClientRect();
                            elements.push({
                                type: 'news-item',
                                element: item,
                                parent: group,
                                top: rect.top - containerRect.top,
                                bottom: rect.bottom - containerRect.top,
                                height: rect.height
                            });
                        });
                    });

                    // 添加新增新闻部分
                    if (newSection) {
                        const rect = newSection.getBoundingClientRect();
                        elements.push({
                            type: 'new-section',
                            element: newSection,
                            top: rect.top - containerRect.top,
                            bottom: rect.bottom - containerRect.top,
                            height: rect.height
                        });
                    }

                    // 添加footer
                    const footerRect = footer.getBoundingClientRect();
                    elements.push({
                        type: 'footer',
                        element: footer,
                        top: footerRect.top - containerRect.top,
                        bottom: footerRect.bottom - containerRect.top,
                        height: footer.offsetHeight
                    });

                    // 计算分割点
                    const segments = [];
                    let currentSegment = { start: 0, end: 0, height: 0, includeHeader: true };
                    let headerHeight = header.offsetHeight;
                    currentSegment.height = headerHeight;

                    for (let i = 1; i < elements.length; i++) {
                        const element = elements[i];
                        const potentialHeight = element.bottom - currentSegment.start;

                        // 检查是否需要创建新分段
                        if (potentialHeight > maxHeight && currentSegment.height > headerHeight) {
                            // 在前一个元素结束处分割
                            currentSegment.end = elements[i - 1].bottom;
                            segments.push(currentSegment);

                            // 开始新分段
                            currentSegment = {
                                start: currentSegment.end,
                                end: 0,
                                height: element.bottom - currentSegment.end,
                                includeHeader: false
                            };
                        } else {
                            currentSegment.height = potentialHeight;
                            currentSegment.end = element.bottom;
                        }
                    }

                    // 添加最后一个分段
                    if (currentSegment.height > 0) {
                        currentSegment.end = container.offsetHeight;
                        segments.push(currentSegment);
                    }

                    button.textContent = `生成中 (0/${segments.length})...`;

                    // 隐藏保存按钮
                    const buttons = document.querySelector('.save-buttons');
                    buttons.style.visibility = 'hidden';

                    // 为每个分段生成图片
                    const images = [];
                    for (let i = 0; i < segments.length; i++) {
                        const segment = segments[i];
                        button.textContent = `生成中 (${i + 1}/${segments.length})...`;

                        // 创建临时容器用于截图
                        const tempContainer = document.createElement('div');
                        tempContainer.style.cssText = `
                            position: absolute;
                            left: -9999px;
                            top: 0;
                            width: ${container.offsetWidth}px;
                            background: white;
                        `;
                        tempContainer.className = 'container';

                        // 克隆容器内容
                        const clonedContainer = container.cloneNode(true);

                        // 移除克隆内容中的保存按钮
                        const clonedButtons = clonedContainer.querySelector('.save-buttons');
                        if (clonedButtons) {
                            clonedButtons.style.display = 'none';
                        }

                        tempContainer.appendChild(clonedContainer);
                        document.body.appendChild(tempContainer);

                        // 等待DOM更新
                        await new Promise(resolve => setTimeout(resolve, 100));

                        // 使用html2canvas截取特定区域
                        const canvas = await html2canvas(clonedContainer, {
                            backgroundColor: '#ffffff',
                            scale: scale,
                            useCORS: true,
                            allowTaint: false,
                            imageTimeout: 10000,
                            logging: false,
                            width: container.offsetWidth,
                            height: segment.end - segment.start,
                            x: 0,
                            y: segment.start,
                            windowWidth: window.innerWidth,
                            windowHeight: window.innerHeight
                        });

                        images.push(canvas.toDataURL('image/png', 1.0));

                        // 清理临时容器
                        document.body.removeChild(tempContainer);
                    }

                    // 恢复按钮显示
                    buttons.style.visibility = 'visible';

                    // 下载所有图片
                    const now = new Date();
                    const baseFilename = `TrendRadar_热点新闻分析_${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}`;

                    for (let i = 0; i < images.length; i++) {
                        const link = document.createElement('a');
                        link.download = `${baseFilename}_part${i + 1}.png`;
                        link.href = images[i];
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);

                        // 延迟一下避免浏览器阻止多个下载
                        await new Promise(resolve => setTimeout(resolve, 100));
                    }

                    button.textContent = `已保存 ${segments.length} 张图片!`;
                    setTimeout(() => {
                        button.textContent = originalText;
                        button.disabled = false;
                    }, 2000);

                } catch (error) {
                    console.error('分段保存失败:', error);
                    const buttons = document.querySelector('.save-buttons');
                    buttons.style.visibility = 'visible';
                    button.textContent = '保存失败';
                    setTimeout(() => {
                        button.textContent = originalText;
                        button.disabled = false;
                    }, 2000);
                }
            }

            document.addEventListener('DOMContentLoaded', function() {
                window.scrollTo(0, 0);
            });
        </script>
    </body>
    </html>
    """

    return html