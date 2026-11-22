#!/usr/bin/env bash
# 一鍵產生 Linux / macOS crontab 設定：每個交易日（週一～週五）於台股與美股盤前自動執行分析並推播
# 使用方式：bash scripts/install_cron.sh --apply

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$(command -v python3)"
LOG_DIR="${PROJECT_DIR}/logs"
mkdir -p "${LOG_DIR}"

CRON_BLOCK=$(cat <<EOF
# === Stock Intel 台美股盤前自動分析與推播 (台北時間 Asia/Taipei) ===
CRON_TZ=Asia/Taipei
# 台股盤前（週一～週五 08:15 台北時間）
15 8 * * 1-5 cd "${PROJECT_DIR}" && "${PYTHON_BIN}" run.py push --session tw_premarket >> "${LOG_DIR}/tw_premarket.log" 2>&1
# 美股盤前（週一～週五 20:45 台北時間）
45 20 * * 1-5 cd "${PROJECT_DIR}" && "${PYTHON_BIN}" run.py push --session us_premarket >> "${LOG_DIR}/us_premarket.log" 2>&1
# === End Stock Intel ===
EOF
)

if [[ "${1:-}" == "--apply" ]]; then
  (crontab -l 2>/dev/null | grep -v "Stock Intel" | grep -v "run.py push" || true; echo "${CRON_BLOCK}") | crontab -
  echo "已成功安裝台美股盤前 crontab 排程！"
  crontab -l
else
  echo "以下為預覽之 crontab 排程（加上 --apply 參數即可自動寫入）："
  echo ""
  echo "${CRON_BLOCK}"
fi
