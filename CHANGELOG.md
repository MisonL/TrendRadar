# 更新日志 (Changelog)

本项目的所有重大变更都记录在此文件中。

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 规范，
版本号遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/spec/v2.0.0.html)。

## [5.1.0] - 2026-01-16

### 新增 (Added)

- **多定时任务支持**: `entrypoint.sh` 现支持在 `CRON_SCHEDULE` 中使用分号 (`;`) 分隔多个 Cron 表达式，允许配置不同时间点的任务。

### 优化 (Improved)

- **Premium 网页 UI**: 全面重构 HTML 报告样式，采用卡片式布局、Indigo-Violet 渐变 Header、毛玻璃效果及 Pill Badges 徽章系统，提升视觉层级与阅读体验。

## [5.0.1] - 2026-01-16

### 修复 (Fixed)

- **核心崩溃修复**: 修复了 RSS 抓取时 `rss_items` 为空导致的 `NoneType` 异常。
- **数据库缺失**: 补全了 `rss_schema.sql` 中缺失的 `rss_crawl_status` 表定义。
- **图片提取增强**: 针对 WallstreetCN 增加了专用 API 抓取逻辑，解决了 SPA 页面无法提取图片的问题。

## [5.0.0] - 2026-01-14

### 新增 (Added)

- **AI 关键词助手 (AI Keyword Assistant)**: 新增 `scripts/generate_keywords.py` 工具，支持通过 LLM 为指定领域自动生成关键词过滤规则，降低配置门槛。
- **配置模板与自动化**: 新增 `config/frequency_words.txt.template` 示例模板；增强脚本支持在配置文件缺失时自动推导。
- **本地图片加速 (Image Cache)**: 新增 `ImageCache` 模块，自动下载并本地缓存新闻封面图，解决防盗链与内网裂图问题。
- **高性能分析 (DuckDB)**: 引入 DuckDB Analytics 引擎，用于处理海量历史数据的毫秒级多维分析与聚合。
- **全异步架构 (Asyncio)**: 爬虫层全面重构为异步 (`httpx` + `asyncio`)，大幅提升 RSS 和热榜抓取性能与并发度。
- **MCP 增强**: 完善 MCP Server 工具链，支持 DuckDB 分析与本地图片路由。

### 优化 (Improved)

- **LLM 服务能力增强**: 在 `LLMService` 中新增通用的 `ask` 接口，支持除打分外的任意 AI 会话需求。
- **环境变量全量文档化**: 对 `.env` 所有的环境变量（共 50+ 项）进行了深度同步，并补全了详尽的中文注释。
- **Git 历史加固**: 彻底清除了 Git 历史中泄露的敏感 Webhook 密钥，并配置了完善的过滤规则预警。
- **代码重构**：重构 `analyzer.py` 核心分析逻辑，将 `count_word_frequency` 函数从 ~400 行精简至 ~100 行，提升可维护性。
- **日志规范化**：统一 `fetcher.py` 中的日志输出，全部使用 `logging` 模块。
- **文档通用化**：README.md 移除财经/A 股硬编码，用户可自由配置关注领域。
- **推送体验**: 升级企业微信推送逻辑，优先使用本地缓存图片作为封面，并实现更完善的消息去重。

### 修复 (Fixed)

- **占位图片**：当文章无有效图片时，企业微信卡片现在会显示默认 Banner 图，而非留空。
- **ImageCache 路径**：修复 Docker 环境下图片缓存的路径解析错误。

### 变更 (Changed)

- **文件清理**：删除冗余文件 `index.html`、`docker/docker-compose-build.yml`。
- **.gitignore**：新增 `*.duckdb`、`*.duckdb.wal`、`.ruff_cache/` 等忽略规则。

## [4.7.2] - 2026-01-13

### 新增 (Added)

- **智能降噪 (LLM Filtering)**: 集成 LLM (Ollama/OpenAI)，支持对新闻标题进行智能评分与摘要，自动过滤垃圾内容。

### 修复 (Fixed)

- **存储管理器**: 修复了 `StorageManager` 中的缩进错误导致清理逻辑失效的问题。
- **依赖缺失**: 补全了 `httpx` 依赖项。

## [4.7.1] - 2026-01-09

### 新增 (Added)

- **财经热点聚焦**：全面重构了 `config/frequency_words.txt`，重点关注 A 股（板块热点、机会捕捉、资金流向）、港股及美股动态。
- **精准定时推送**：在 `.env` 中配置了定时任务，固定在每日 9:00、11:30、14:30 三个关键交易时点推送。
- **项目属性标注**：在文档中明确标注本项目为 `sansan0/TrendRadar` 的独立二开版本。
- **技术架构文档**：新增 `ARCHITECTURE.md`，详细介绍系统设计与工作流。
- **消息去重功能**: 支持配置 `deduplication`，可有效防止重复推送相同新闻（支持 URL 哈希或标题+来源去重）。

### 修复 (Fixed)

- **企微通知样式**：重构了企业微信 Webhook 发送逻辑，升级为 `news`（图文列表）格式，完美复刻公众号卡片样式。
- **数据提取逻辑**：修复了 `senders.py` 中由于热搜数据嵌套结构（`word_groups`）导致的条目解析失败问题。
- **跳转链接优化**：修复了卡片底部“查看更多”和封面图的跳转逻辑，支持局域网 IP 直连访问，移除了 GitHub 的保底链接。
- **Docker 构建配置**：优化了 `docker-compose.yml` 的 `build` 上下文与环境变量透传，解决代码变更未同步至容器的问题。

### 变更 (Changed)

- **文档重构**：全面精简了 `README.md`，将技术细节移至 ARCHITECTURE.md，保持主页清爽专业，并移除了所有英文文档。
