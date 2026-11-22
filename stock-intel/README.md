# 智策股市情報與多空推演系統 v2.0（Stock Intel）

一套專為**美股 × 台股跨市場決策**打造的自動化股市情報系統：覆蓋**全球 7 大區域 6 種語系財經新聞**、串接**台灣證交所三大法人買賣超**、提供**基本面 × 技術面優劣勢診斷**、**2 年期量化策略回測**，以及**每日台股／美股盤前自動排程推播**。

## 核心功能亮點

1. **全球跨語系財經情報網與官方公告歸因（20 組免費 RSS + TWSE 官方重訊、7 大板塊、6 種語系）**
   - **北美**：CNBC、MarketWatch、Google Business US、美股企業合約／FDA／SEC 監管快訊 (`en`)
   - **歐洲**：BBC Business、The Guardian、Google UK (`en`) / 德國 (`de`) / 法國 (`fr`)
   - **日本與韓國**：Google Japan (`ja`)、Google Korea (`ko`)
   - **亞太新興與中東**：Google Singapore (`en`)、Google India (`en`)、CNBC World、Al Jazeera Global
   - **台灣**：Google 財經／科技／合約訂單快訊 + **TWSE 上市公司官方重大訊息 (`t187ap04_L`)**
   - **產業利多 × 利空雙排行與消息面要素**：自動偵測合約／併購／官方核准／勝訴（利多）與監管調查／出口管制／高層危機／拋售／衝突（利空），白話標示為何利多或為何利空。

2. **台股三大法人買賣超籌碼系統（TWSE 官方資料）**
   - **大盤籌碼（`BFI82U`）**：即時抓取外資及陸資、投信、自營商（含避險）買賣超金額（億元），自動納入大盤多空推演。
   - **個股籌碼（`T86`）**：即時抓取全體上市個股三大法人買賣超張數，自動辨識「土洋合擊買超」、「投信逆勢護盤」、「外資提款」並生成籌碼評分與優劣勢。

3. **2 年期量化策略回測驗證（無未來函數、含真實手續費／證交稅）**
   - 自動針對每檔美股／台股以近 2 年日線驗證 3 大策略並與買進持有基準對比：
     - `均線多頭趨勢策略 (MA5/20/60 + 8% 移動停損)`
     - `RSI + MACD 動能反轉策略`
     - `智策綜合技術評分策略`
   - 輸出總報酬、超額 Alpha、年化報酬、最大回撤、夏普比率、勝率、交易次數、當前持倉訊號與互動雙線權益曲線。

4. **每日台美股盤前 LINE Flex 卡片定時推播（台北時間 `Asia/Taipei`）**
   - **台股盤前（週一～週五 08:15）**與**美股盤前（週一～週五 20:45）**自動推播彩色 LINE Flex 卡片（含產業利多推薦與產業利空警戒及消息面事由）。詳細設定請見 `docs/LINE_SETUP.md`。
   - 同時相容 Telegram Bot、Discord Webhook 與 Email SMTP。

## 快速指令

```bash
cd stock-intel

# 1. 執行完整全球分析（全球新聞＋官方重訊＋利多/利空產業排行＋三大法人＋策略回測）
python3 run.py analyze

# 2. 單股深度診斷與 2 年期策略回測（支援任意美股／台股）
python3 run.py stock 2330
python3 run.py backtest NVDA

# 3. 驗證 LINE Token 並立刻發送測試 Flex 卡片（或預覽盤前簡報）
python3 run.py test-line --send
python3 run.py push --session tw_premarket --dry-run

# 4. 啟動每日盤前自動排程器（常駐背景，週一～週五 08:15 & 20:45 台北時間）
python3 run.py schedule

# 5. 啟動互動式網頁儀表板伺服器
python3 run.py serve --port 8080
```

## 長期每天自動盤前推播的 3 種部署方式

1. **GitHub Actions 免費雲端排程（推薦，無需開電腦）**
   - 專案已內建 `.github/workflows/premarket_push.yml`（已設定好週一～週五台北時間 08:15 與 20:45 自動觸發）。
   - 將專案推送至您的 GitHub 儲存庫後，在 **Settings → Secrets and variables → Actions** 填入推播金鑰（如 `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID` 或 `DISCORD_WEBHOOK_URL` / `LINE_CHANNEL_ACCESS_TOKEN`）即可零成本自動推播。
2. **Linux / macOS / NAS 本機 Crontab**
   - 先設定 `.env` 推播金鑰，再執行 `bash scripts/install_cron.sh --apply` 一鍵寫入排程。
3. **常駐 Python 排程器（任何作業系統）**
   - 執行 `python3 run.py schedule`（或搭配 `tmux` / `systemd` 常駐運行）。

> **免責聲明**：本系統所提供之全球新聞推演、三大法人籌碼、策略回測與個股分析僅供量化研究與資訊參考，不構成任何投資買賣建議；歷史回測績效不代表未來獲利。
