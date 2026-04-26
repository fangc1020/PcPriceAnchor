# JD 反爬攻克求助文档

## 目标

从 `search.jd.com` 抓取 DDR5/DDR4 内存条搜索列表，提取：SKU ID、标题、价格、详情链接。

## 环境

- macOS ARM64，深圳（大陆 IP）
- Python 3.12 + httpx + Playwright 1.58 + Chromium 145
- 项目路径：`/Users/fc/PcPriceAnchor`
- venv：`.venv/bin/python`
- 爬虫代码：`price_monitor/crawlers/jd/`

## 已探明的关键事实

### 1. `p.3.cn` 价格 API 是内网地址（不可用）

```bash
dig +short p.3.cn
# → 172.28.59.58, 10.199.200.133, 172.26.101.78, 172.18.230.51
```

全是 RFC 1918 私有 IP。只有京东 CDN 边缘节点能访问，外部网络（包括大陆家庭宽带）不通。curl 和浏览器 fetch 均返回 `Failed to fetch` / `ConnectTimeout`。**此路不通。**

### 2. `api.m.jd.com` 是公网可达的，但价格返回加密

该域名可从外部访问。但关键接口：

- `pc_detailpage_wareBusiness` — 返回 **HTTP 403**（需要特定签名/Cookie）
- `pc_new_cdpPromotionQuery` — 返回 `{}` 空数据
- 另有 POST 到 `api.m.jd.com/` 的请求返回 base64 编码的疑似加密价格数据，无法解码

### 3. 搜索结果页强制要求登录

| 访问方式 | `www.jd.com` | `search.jd.com` | `item.jd.com` |
|---------|-------------|-----------------|---------------|
| httpx (无 Cookie) | 200 OK | 302 → `cfe.m.jd.com/risk_handler` | 未测试 |
| httpx + 浏览器头 + Referer | 200 OK | 302 → `risk_handler` | 未测试 |
| Playwright (裸 Chromium) | 200 → JS 重定向到 `passport.jd.com/new/login.aspx` | 同左 | 可访问但价格显示 ¥0 |
| Playwright + add_init_script 隐藏 webdriver | 同左 | 同左 | 同左 |
| Playwright + playwright_stealth | www.jd.com 不跳转（cookie 有效时） | 仍然跳转 passport | 未测试 |

### 4. 登录态的关键发现

- 用户在 Playwright 窗口手动扫码登录成功，`www.jd.com` 可正常浏览
- Cookie 保存后（`.jd_cookies.json`），下次启动 `www.jd.com` 不跳登录
- **但导航到 `search.jd.com/Search` 仍然跳转 passport**，即使刚登录
- 京东搜索页似乎有独立的 session 验证，或检测到自动化浏览器特征后才触发登录墙
- `item.jd.com/{skuId}.html` **未登录时也能打开**，但价格显示"¥0"或"京 东 价"空白

### 5. 价格数据流分析

通过 Playwright 拦截 `item.jd.com` 页面上所有 200 响应：

```
api.m.jd.com/ (多次 POST) → 返回 JSON，部分包含加密 data 字段
api.m.jd.com/new/cdpPromotionQuery → 返回空对象 {}
```

价格没有出现在任何 API 响应中。推测 JD 通过以下方式之一加载价格：
- WebSocket 推送
- `<img>` 标签图片价格（需 OCR）
- Canvas 渲染
- 需要特定 `functionId` + 签名参数

## 已尝试 / 已废弃的方案

| 方案 | 结果 | 废弃原因 |
|------|------|---------|
| httpx → `search.jd.com` | 302 风控 | 无 Cookie |
| httpx + 模拟浏览器头 | 302 风控 | 缺 TLS 指纹 |
| httpx + Cookie (从浏览器手动提取) | Cookie 中无 pt_key/pt_pin | JD 可能改了 Cookie 命名或用 HttpOnly |
| Playwright → `search.jd.com` | 跳 passport 登录 | 检测到自动化 |
| Playwright + `--disable-blink-features=AutomationControlled` | 跳 passport | 不够 |
| Playwright + `add_init_script` 隐藏 webdriver/plugins/languages | 跳 passport | 不够 |
| Playwright + `playwright_stealth` (16 项 evasion) | www.jd.com 正常，search.jd.com 仍跳登录 | 搜索页有额外检测 |
| Playwright 从首页搜索框输入 → Enter | 搜索框 `#key` 未找到 | jd.com 首页可能 JS 动态渲染搜索框 |
| `page.evaluate(fetch('p.3.cn/...'))` | Failed to fetch | 内网地址 |
| `page.evaluate(fetch('api.m.jd.com/...'))` | 403 | 缺签名 |
| curl → `api.m.jd.com` | 403，响应头含 `x-rp-sdtoken` | 缺指纹/Cookie |

## 当前代码状态

三个爬虫实现（都在 `price_monitor/crawlers/jd/`）：

| 文件 | 引擎 | 状态 |
|------|------|------|
| `search.py` | httpx | 被风控 302 拦截 |
| `playwright_search.py` | Playwright + 手动登录 | 登录后搜索仍跳 passport |
| `stealth_crawler.py` | Playwright + stealth + cookie 持久化 | cookie 复用成功，搜索仍跳 passport |

CLI 入口：`python -m price_monitor.main once --dry-run --engine [httpx|playwright|stealth] --keyword "DDR5 内存条"`

## 建议尝试的方向

1. **移动端 API 逆向**：JD App 使用的 API 端点可能有不同鉴权方式。抓包 JD Android/iOS App 获取真实 API endpoint 和签名算法
2. **商品详情页价格解析**：`item.jd.com` 无需登录即可访问。如果能在 HTML 中找到价格的渲染位置（可能在 `<script>` JSON、CSS 伪元素、或 lazyload 的 XHR），就可绕过搜索页
3. **真正的 Chrome Profile 复用**：用 Playwright 的 `channel="chrome"` 启动用户本机真实 Chrome，继承完整登录态、书签、扩展等浏览器指纹，可能比 Chromium + stealth 更像真人
4. **第三方数据源**：慢慢买、什么值得买等比价网站可能有京东价格历史数据
5. **京东开放平台 API**：`open.jd.com` 的商家 API 可能有价格查询接口（需要商家资质）
6. **OCR 方案**：如果价格确实以图片形式展示，用 Playwright 截图 + OCR 提取数字
