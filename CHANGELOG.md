# 更新日志 (Changelog)

本项目的所有重大变更都记录在此文件中。

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 规范，
版本号遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/spec/v2.0.0.html)。

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
