# JD 反爬解决方案：真实 Chrome CDP 接管

## 背景与问题

京东对自动化浏览器的检测机制极强：

- `search.jd.com` 对 Playwright/Chromium 触发 passport 登录或验证码（"认证魔方"）
- 手动扫码登录、接听语音验证码后仍反复弹出登录界面
- `item.jd.com` 目前也要求登录
- `playwright-stealth` 的 16 项反检测均被突破

**根本原因**：Playwright 内置 Chromium 的浏览器指纹（User-Agent、渲染引擎特征、Canvas 指纹、字体列表等）与真实用户 Chrome 存在可识别差异，京东后端可以区分。

## 解决思路

**不模拟真实浏览器，直接使用真实浏览器。**

Chrome 支持 `--remote-debugging-port` 参数，暴露 Chrome DevTools Protocol (CDP) 接口。
Playwright 可以通过 `connect_over_cdp()` 接管这个已运行的 Chrome，在其中执行操作。

对京东服务器而言：
- 请求来自用户本机真实 Chrome（非 Chromium）
- 完整继承用户的登录 Cookie、浏览器指纹、历史记录等
- 与正常用户手动操作完全一致，无法区分

## 验证结果（2026-04-27）

测试环境：macOS ARM64，深圳大陆 IP，Chrome 147

```
第 1 页：DDR5 内存条 - 商品搜索 - 京东  ✓ 提取到 60 个商品
第 2 页：DDR5 内存条 - 商品搜索 - 京东  ✓ 提取到 60 个商品
总计：120 个商品，其中 120 个有价格（非零）
示例：海力士 DDR5 8GB ¥849.00 / 光威 16GB DDR5 6000 ¥1299.00
```

## 文件说明

| 文件 | 作用 |
|---|---|
| `price_monitor/crawlers/jd/cdp_crawler.py` | JdCdpCrawler 类，实现 BaseCrawler 接口 |
| `scripts/start_chrome.sh` | 启动带调试端口的真实 Chrome |
| `scripts/daily_crawl.sh` | 每日采集脚本（可接 cron） |

## 使用方法

### 第一步：启动 Chrome

```bash
bash scripts/start_chrome.sh
```

脚本会：
1. 检测 9222 端口是否已有 Chrome，有则跳过
2. 关闭现有 Chrome 实例
3. 启动带 `--remote-debugging-port=9222` 的 Chrome

**首次运行**：在弹出的 Chrome 窗口中打开 `https://www.jd.com`，手动登录（扫码或账号密码）。

> ⚠️ Chrome profile 存储在 `/tmp/chrome_jd_profile`，Mac 重启后 `/tmp` 清空，需重新登录。
> 如需持久化，修改 `start_chrome.sh` 中的 `PROFILE_DIR` 为固定路径（如 `~/.chrome_jd_profile`）。

### 第二步：运行采集

```bash
source .venv/bin/activate

# dry-run（不写 DB，只打印结果，用于验证）
python -m price_monitor.main once --engine cdp --keyword "DDR5 内存条" --pages 10 --dry-run

# 正式采集（写 DB，需要 PostgreSQL + TimescaleDB 已就绪）
python -m price_monitor.main once --engine cdp --keyword "DDR5 内存条" --pages 10
```

### 每日自动化

```bash
# 手动触发
bash scripts/daily_crawl.sh

# 设置 cron（每天 8:05 自动运行）
crontab -e
# 添加：
5 8 * * * /bin/bash /Users/fc/PcPriceAnchor/scripts/daily_crawl.sh
```

> ⚠️ **cron 限制**：macOS cron 在后台无桌面 session，Chrome GUI 无法启动。
> 推荐方案：用 macOS **launchd** 替代 cron，或在用户登录后手动运行 `daily_crawl.sh`。
> launchd 配置参考：[Apple 官方文档](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/ScheduledJobs.html)

## JD 搜索页 DOM 结构（2025 年新版）

JD 在 2025 年将搜索页从 jQuery 重构为 React + CSS Modules。关键变化：

| 旧版（已失效） | 新版（当前有效） |
|---|---|
| `.gl-item[data-sku]` | `[data-sku]`（通用属性，60个/页）|
| `.p-name em` | `span[class*="_text_"][title]` |
| `.p-price i` | `[class*="_price_"] span`（内含数字）|

**CSS Modules 哈希问题**：新版 class 名含构建时哈希，如 `_text_1k2fi_48`。
爬虫使用 `[class*="_text_"]` 属性选择器匹配，只依赖特征前缀词，不依赖完整哈希，
因此 JD 前端小版本更新时通常不会失效。

**若某次更新后提取到 0 条商品**，排查步骤：
1. 手动用 Chrome 打开搜索页，F12 开发者工具，检查商品卡片的 HTML 结构
2. 确认 `[data-sku]` 属性是否仍然存在
3. 找到标题和价格的新 class 名，更新 `cdp_crawler.py` 中的 `_extract_products()` 方法

## 频率控制

当前配置：
- 每页抓取后随机等待 2-4 秒
- 每日只运行一次（`daily_crawl.sh`）
- 远低于 JD 的 30 req/min 限制

日采集规模估算：
- 内存条品类约 10-15 页 × 60 条/页 = 600-900 个商品
- 全部价格 ≈ 900 次请求，分散在约 1 分钟内完成
- 对 JD 来说等同于一个用户浏览 15 页搜索结果

## 已知限制

1. **需要本机 Chrome**：只能在有 Chrome 的 Mac 上运行，不能在无头服务器部署（除非用虚拟显示器 Xvfb + Linux Chrome）
2. **需要手动登录（首次）**：profile 持久化后可免登录，但 Mac 重启后 `/tmp` 清空需重新登录
3. **单机单账号**：大规模并发需要多账号 + 多机，当前 MVP 不需要
4. **价格实时性**：每日一次，不适合秒杀/限时价格监控

## 后续接入慢慢买（历史数据补充）

CDP 爬虫只能采集今日起的数据。如需历史趋势（过去数月），可从慢慢买获取：

- 项目：[manmanbuy_history](https://github.com/OrbitRush/manmanbuy_history)
- 原理：慢慢买聚合了京东历史价格，逆向其 JS 签名后可批量拉取
- 用途：一次性导入历史数据，之后由 CDP 爬虫维护每日增量

具体接入步骤待实现（P5 阶段）。

## DeepSeek 执行清单

以下是交给 DeepSeek 执行的完整任务列表：

### 已完成 ✅
- [x] `JdCdpCrawler` 类实现（`price_monitor/crawlers/jd/cdp_crawler.py`）
- [x] `start_chrome.sh` 启动脚本
- [x] `daily_crawl.sh` 每日采集脚本
- [x] `main.py` 接入 `--engine cdp` 选项（默认引擎已改为 cdp）

### 待完成 🔲

**P1：验证完整流水线（dry-run）**
```bash
bash scripts/start_chrome.sh
# 在 Chrome 中登录京东
python -m price_monitor.main once --engine cdp --keyword "DDR5 内存条" --pages 10 --dry-run
```
预期：输出 600+ 条商品的品牌、规格、价格解析结果，无 ERROR 日志。

**P2：接入数据库，正式写入**
1. 启动 PostgreSQL + TimescaleDB（Docker 推荐）：
   ```bash
   docker run -d --name timescaledb \
     -e POSTGRES_PASSWORD=yourpassword \
     -p 5432:5432 \
     timescale/timescaledb:latest-pg16
   ```
2. 配置 `.env`（参考 `.env.example`）
3. 运行 `alembic upgrade head` 建表
4. 去掉 `--dry-run` 正式采集

**P3：设置每日自动化**
- 修改 `scripts/daily_crawl.sh` 中的 `--dry-run` 去掉
- 配置 macOS launchd 定时任务（或登录后手动触发）

**P4：慢慢买历史数据导入（可选）**
- 参考 [manmanbuy_history](https://github.com/OrbitRush/manmanbuy_history)
- 编写导入脚本，将历史数据转换为 `CleanProduct` 格式写入 DB

**P5：分析报告**
- DB 有数据后运行：`python -m price_monitor.main analyze`
- 配置飞书 Webhook（`.env` 中 `FEISHU_WEBHOOK_URL`）推送日报
