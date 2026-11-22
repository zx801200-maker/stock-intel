# LINE 每日盤前自動推播設定指南（5 分鐘完成・完全免費）

> 由於舊版 LINE Notify 已於 2025 年 3 月停止服務，本系統已直接採用官方新版 **LINE Messaging API**，並內建**精美彩色 Flex Message 投資決策卡片**。
> LINE 官方帳號免費方案每月提供 **200 則免費推播訊息**；台股盤前（08:15）＋美股盤前（20:45）每個月約 44 則，**完全免費、免綁信用卡！**

---

## 步驟一：建立免費 LINE 官方帳號並取得 Token（約 3 分鐘）

1. 前往 [LINE Developers Console](https://developers.line.biz/console/)，使用您的個人 LINE 帳號登入。
2. 點擊 **Create a new provider**（例如命名為 `StockIntel`）。
3. 點擊 **Create a Messaging API channel**，填入基本名稱（例如「智策盤前助手」），完成建立。
4. 進入剛建立的 Channel，切換至 **Messaging API** 分頁：
   - 用手機 LINE 掃描頁面上的 **QR Code**，把這個機器人加為好友。
   - 滑到最下方找到 **Channel access token (long-lived)**，點擊 **Issue** 發行，並複製這串 Token。
5. （建議）前往 [LINE Official Account Manager](https://manager.line.biz/) → 回應設定 → 關閉「自動回應訊息」，避免訊息干擾。

> **小技巧（免查 User ID！）**：如果您是這個機器人唯一的好友，**`LINE_USER_ID` 可以直接留空**！程式會自動使用 LINE `Broadcast` API 將盤前卡片推播給您，完全不需要另外設定 Webhook 查 User ID。

---

## 步驟二：填入設定並一鍵測試推播

### 方式 A：在您的本機電腦／NAS／VPS 執行

```bash
cd stock-intel
cp .env.example .env
```

編輯 `.env`，貼上您剛剛複製的 Token：

```env
LINE_CHANNEL_ACCESS_TOKEN=貼上您的Long-lived-Token
LINE_USER_ID=
LINE_FORMAT=flex
```

立刻測試連線並發送第一張台股盤前 Flex 卡片到您的 LINE：

```bash
python3 run.py test-line --send
```

確認手機 LINE 收到彩色決策卡片後，選擇任一種方式啟動每日自動盤前排程：

- **Linux / macOS 一鍵寫入 Crontab**（週一～週五台北時間 08:15 & 20:45）：
  ```bash
  bash scripts/install_cron.sh --apply
  ```
- **或直接常駐啟動排程器**（Windows / macOS / Linux 通用）：
  ```bash
  python3 run.py schedule
  ```

---

### 方式 B：免開電腦！使用 GitHub Actions 免費雲端排程（最推薦）

1. 將整個 `stock-intel` 資料夾上傳到您的個人 **GitHub Private Repository**。
2. 進入 GitHub 儲存庫頁面 → **Settings** → **Secrets and variables** → **Actions** → 點擊 **New repository secret**。
3. 新增 Secret：
   - Name: `LINE_CHANNEL_ACCESS_TOKEN`
   - Secret: 貼上您的 Long-lived Token
   - （選配）若想同時啟用 AI 深度推演，再新增 `GEMINI_API_KEY` 或 `OPENAI_API_KEY`。
4. 切到 **Actions** 分頁 → 選擇 **「Stock Intel 台美股盤前自動分析與推播」** → 點擊 **Run workflow** 立刻試跑一次！
5. 之後系統會在每個週一～週五的 **台北時間 08:15（台股盤前）** 與 **20:45（美股盤前）** 自動執行全球多語分析並推播 Flex 卡片到您的 LINE。

---

## 常見問題

- **如何推播到 LINE 投資群組？**
  把機器人邀請進群組後，將 FastAPI 伺服器對外（或透過 ngrok）連上 `/api/line/webhook`，在群組發一則訊息即可於伺服器日誌看到 `groupId`（`C...` 開頭），填入 `LINE_USER_ID=Cxxxx` 即可。
- **想要改用純文字格式？**
  在 `.env` 設定 `LINE_FORMAT=text` 即可。
