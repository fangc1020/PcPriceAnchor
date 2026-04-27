#!/bin/bash
# 每日采集脚本 — 手动执行，每次采集 1 个价格快照。
#
# 用法：
#   bash scripts/daily_crawl.sh                        # 默认关键词 + 2 页
#   bash scripts/daily_crawl.sh "DDR5 32G 套装"        # 自定义关键词
#   bash scripts/daily_crawl.sh "DDR5 6000 16G" 1      # 自定义关键词 + 1 页
#
# 前置条件：
#   - Chrome 已通过 scripts/start_chrome.sh 启动并登录京东
#   - Docker 已启动（docker compose up -d）
#
# 每次执行会在 DB 中新增一个价格快照，积累多日后趋势分析即可显示涨跌。

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${PROJECT_DIR}/.venv/bin/activate"
LOG_DIR="${PROJECT_DIR}/logs"
LOG_FILE="${LOG_DIR}/crawl_$(date +%Y-%m-%d).log"

KEYWORD="${1:-DDR5 内存条}"
PAGES="${2:-2}"

mkdir -p "${LOG_DIR}"

echo "===== $(date '+%Y-%m-%d %H:%M:%S') 开始采集（关键词: ${KEYWORD}, ${PAGES} 页）=====" | tee -a "${LOG_FILE}"

# 1. 确保 Chrome 已启动
bash "${PROJECT_DIR}/scripts/start_chrome.sh" >> "${LOG_FILE}" 2>&1
sleep 2

# 2. 采集
source "${VENV}"
python -m price_monitor.main once \
    --engine cdp \
    --keyword "${KEYWORD}" \
    --pages "${PAGES}" \
    2>&1 | tee -a "${LOG_FILE}"

# 3. 输出简要分析
python -m price_monitor.main analyze 2>&1 | head -30 | tee -a "${LOG_FILE}"

echo "===== $(date '+%Y-%m-%d %H:%M:%S') 完成 =====" | tee -a "${LOG_FILE}"
echo "完整报告：python -m price_monitor.main analyze" | tee -a "${LOG_FILE}"
