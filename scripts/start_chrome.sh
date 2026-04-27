#!/bin/bash
# 启动带 CDP 调试端口的真实 Chrome，供爬虫接管。
#
# 使用方法：
#   bash scripts/start_chrome.sh
#
# 首次运行：在弹出的 Chrome 窗口中手动登录京东，之后无需重复登录
#（profile 存储在 /tmp/chrome_jd_profile，重启 Mac 后 /tmp 会清空，需重新登录）。
#
# 若想让 profile 持久化，将 PROFILE_DIR 改为项目内路径，例如：
#   PROFILE_DIR="$HOME/.chrome_jd_profile"

PROFILE_DIR="/tmp/chrome_jd_profile"
PORT=9222
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# 检查 Chrome 是否已在监听
if curl -s "http://localhost:${PORT}/json/version" > /dev/null 2>&1; then
    echo "✓ Chrome 已在端口 ${PORT} 运行，无需重新启动。"
    exit 0
fi

# 关闭已有 Chrome 实例（防止端口冲突）
pkill -f "Google Chrome" 2>/dev/null
sleep 1

echo "启动 Chrome，调试端口: ${PORT}，profile: ${PROFILE_DIR}"
"${CHROME}" \
    --remote-debugging-port="${PORT}" \
    --user-data-dir="${PROFILE_DIR}" \
    --no-first-run \
    --no-default-browser-check \
    &

# 等待 Chrome 就绪（最多 10 秒）
for i in $(seq 1 10); do
    if curl -s "http://localhost:${PORT}/json/version" > /dev/null 2>&1; then
        echo "✓ Chrome 已就绪（${i}s）"
        echo ""
        echo "请在弹出的 Chrome 窗口中登录京东（https://www.jd.com），"
        echo "登录完成后返回终端运行爬虫。"
        exit 0
    fi
    sleep 1
done

echo "❌ Chrome 启动超时，请手动检查。"
exit 1
