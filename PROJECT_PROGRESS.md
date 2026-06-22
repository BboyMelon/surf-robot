# 🌊 浪況機器人專案進度

## 專案資訊
- **專案名稱**：LINE 浪況自動訂閱與回報機器人
- **專案路徑**：`/Users/melon/Downloads/melon-agent/surf_robot/`
- **最後更新**：2026-06-22
- **部署網址**：https://surf-robot.onrender.com
- **Streamlit 後台**：https://surf-robot-svyi2lsrzaeuxxgxrzxsys.streamlit.app/
- **GitHub**：https://github.com/BboyMelon/surf-robot

> 這份文件只記錄「現況」跟「待辦」，不放任何金鑰實際值（見下方〈安全性提醒〉）。實作細節、踩坑記錄看 commit message 跟對應的 Claude 記憶檔。

---

## ⚠️ 安全性提醒
- 所有金鑰只存在 `.env`（本機，gitignore）、Render Environment、Streamlit Secrets、GitHub Secrets 這四個地方，**不要**寫進任何會 commit 的檔案（包含這份文件）。
- 本文件舊版曾經把 `CWA_API_KEY`、`LINE_CHANNEL_SECRET` 實際值寫在表格裡並 commit 進 git 歷史，已於 2026-06-22 移除目前版本的明文，但**歷史紀錄中還留著舊值**。repo 是 Private（只有自己能看到），實際風險低，純粹是好習慣。`LINE_CHANNEL_SECRET` 已於 2026-06-22 完成輪替（Render + 本機 .env 已更新，傳 LINE 訊息測試正常）；`CWA_API_KEY` 是免費氣象資料、風險更低，還沒輪替，不急。
- `.gitignore` 已排除：`.env`、`*.json`（Google service account 金鑰）、`api權限.txt`、`*.png`、`.DS_Store`、`surf_bot.db`。

---

## 技術架構

| 元件 | 技術 | 說明 |
|------|------|------|
| 後端 Webhook | Python Flask + gunicorn | LINE 事件接收、即時查詢、背景排程執行緒 |
| 後台管理 | Python Streamlit | 訂閱名單 / Surfer 檔案 / 推播管理按鈕，獨立部署於 Streamlit Community Cloud |
| 資料同步 | `sync_to_sheets.py` + gspread | 每日把訂閱資料同步進 Google Sheet，獨立跑在 GitHub Actions runner |
| 雲端資料庫 | Supabase (PostgreSQL) | `members` / `groups` / `profiles` 三張表 |
| 主要浪況資料 | CWA `O-B0075-001` | 浮標站即時海象（波高/週期/風向/潮位） |
| 備援浪況資料 | Open-Meteo Marine API | CWA 失敗時自動切換，免金鑰 |
| 潮汐預報 | CWA `F-A0021-001` | 15 浪點對應最近潮汐站，查單一浪點時附今日滿潮/乾潮時刻 |
| 颱風資料 | CWA `W-C0034-005` | 距台灣 1000km 內偵測到新熱帶氣旋即推播 |
| 推播 | LINE Messaging API | Push（排程廣播）+ Reply（互動查詢） |
| 部署 | Render.com（Free） | gunicorn 單 worker；Free 方案會 spin-down，靠 GitHub Actions 每 5 分鐘 ping `/health` 維持喚醒 |
| CI/CD | GitHub Actions（4 個 workflow） | `deploy.yml`（push main 自動部署）/ `keep_alive.yml`（防 spin-down）/ `broadcast.yml`（定時觸發廣播端點）/ `sync_sheets.yml`（定時同步 Sheet） |

---

## 檔案結構

```
surf_robot/
├── .env / .env.example       金鑰設定（.env 不進 git）
├── .gitignore
├── Procfile                  gunicorn webhook:app（Render 只跑這個）
├── config.py                 浪點設定、潮汐站對應表、陸風方向、GoOcean 分級
├── db.py                     Supabase / SQLite 雙後端資料層
├── broadcast.py              抓資料、組訊息、廣播、警戒、潮汐查詢
├── webhook.py                LINE Webhook + 指令處理 + 背景排程
├── app.py                    Streamlit 後台（另外部署，Render 不會跑這個）
├── sync_to_sheets.py         Supabase → Google Sheet 同步腳本
├── setup_richmenu.py         LINE 圖文選單產生 + 上傳腳本（本機手動執行）
├── requirements.txt
├── .github/workflows/        deploy.yml / keep_alive.yml / broadcast.yml / sync_sheets.yml
└── PROJECT_PROGRESS.md        本文件
```

---

## Supabase 資料表

| 表 | 欄位 |
|------|------|
| `members` | `id, email, line_id (UNIQUE), status, created_at` |
| `groups` | `id, group_id (UNIQUE), status, joined_at` |
| `profiles` | `id, line_id (UNIQUE), nickname, gender, surf_years, board_type, fav_spots, display_name, updated_at` |

---

## 監測浪點（共 15 個）

| 地區 | 浪點 | 浮標站 |
|------|------|--------|
| 🔵 北部 | 金山沙珠灣 / 中角灣 | `46778A` |
| 🔵 北部 | 翡翠灣 | `C6AH2` |
| 🔵 北部 | 烏石港 / 宜蘭外澳 | `46757B` |
| 🟡 中部 | 松柏港福德里 | `46714D` |
| 🟡 中部 | 外埔漁港 | `COMC08` |
| 🟠 東部 | 花蓮北濱公園 / 花蓮環保公園 | `46706A` |
| 🟠 東部 | 台東金樽 / 台東東河 | `46761F` |
| 🔴 南部 | 台南漁光島 | `46699A` |
| 🔴 南部 | 恆春南灣 / 恆春佳樂水 | `46694A` |
| 🔴 南部 | 恆春九鵬 | `C6S94` |

潮汐站對應表見 `config.py` 的 `TIDE_STATION_MAP`。

---

## LINE 圖文選單（2×2 格，2026-06-22 改版）

| 格 | 名稱 | 觸發文字 |
|----|------|---------|
| 1 | 🔍 即時浪況查詢 | `🔍 即時浪況查詢` |
| 2 | 📝 Surfer 檔案建立 | `📝 Surfer 檔案建立` |
| 3 | 📚 專業海象觀測網 | `📚 專業海象觀測網`（含 CWA / NODASS / Swell Eye / Windy 4 個連結） |
| 4 | 📋 加入浪況訂閱會員 | `📋 加入浪況訂閱會員`（彈出訂閱邀請卡片，連到 Streamlit 表單） |

風格：藍→青→珊瑚→金黃漸層 + 底部波浪剪影。目前選單 ID 記在 Claude 記憶裡，換版前先用 `setup_richmenu.py` 的 `make_image()` 產圖確認過設計再正式上傳。

---

## LINE 指令總覽

| 使用者輸入 | 機器人回應 |
|-----------|-----------|
| `help` / `指令` / `說明` | 指令總覽 |
| `總覽` / `全台` | 全台每區一行精簡摘要 |
| 地區名稱（北部/中部/東部/南部/花蓮/台東/恆春/墾丁） | 該地區所有浪點 |
| 浪點名稱（烏石港、外澳、金樽…） | 單點即時浪況 + 今日潮汐時刻 |
| `明日` / `明日預報` | 明日完整預報 |
| `訂閱` / `立即訂閱` / `加入訂閱` | 訂閱邀請卡片 |
| `性別：…\n浪齡：…\n名稱：…` 格式 | 建立 Profile（已建檔需在開頭加「修改」才能覆寫） |
| `我的資料` / `我的檔案` | 查詢目前 Surfer 檔案 |
| `我的ID` | 回覆 LINE 顯示名稱 |

---

## 排程任務

| 觸發方式 | 任務 | 頻率 |
|------|------|------|
| GitHub Actions `broadcast.yml` | `broadcast()` 全台浪況廣播 | 每日台灣 05:00 + 15:00 |
| Render 背景執行緒 | `check_swell_alerts()` 長浪警戒 | 每 3 小時 |
| Render 背景執行緒 | `check_typhoon_alerts()` 颱風警報 | 每 1 小時 |
| GitHub Actions `sync_sheets.yml` | Supabase → Google Sheet 同步 | 每日台灣 04:30 |
| GitHub Actions `keep_alive.yml` | ping `/health` 防 spin-down | 每 5 分鐘 |

---

## 已完成功能（按主題彙總）

- **核心推播**：15 浪點、每日早晚 2 次廣播（通用版+個人化版）、長浪警戒（6h de-dup）、颱風警報（距台 1000km 內）、明日預報、潮汐時刻
- **查詢功能**：浪點/地區查詢、全台總覽、明日預報、潮汐時刻、Surfer 檔案查詢
- **Surfer 檔案**：性別/浪齡/版型/常衝浪點/名稱，`display_name` 自動記錄 LINE 名稱，防重複建檔覆寫（需「修改」關鍵字）
- **後台**：Streamlit 管理介面（訂閱名單/Profile 表格/推播按鈕），Google Sheet 唯讀同步
- **部署**：Render + Streamlit Cloud 雙部署、GitHub Actions 4 個 workflow 全自動化
- **圖文選單**：LINE Rich Menu 4 按鈕，2026-06-22 改版為海洋衝浪風格
- **2026-06-22 程式碼優化**：`CWA_API_KEY` 改走環境變數、警戒推播時區修正（`TW_TZ`）、浪齡 0 誤判修正
- **2026-06-22 CWA SSL 修復**：Render 上 CWA API 連線失敗問題（見上方待辦清單說明），改用 `curl` 子行程解決；潮汐時刻顯示排版優化（兩欄分行，原本一行擠 4 個時刻不好讀）

---

## 待辦清單

### 下一步
- [ ] **今日最佳浪點推薦擴充**：目前已有基本版（`find_best_spots()`），可再優化排序權重
- [ ] **重複邏輯整併**：`build_report()` / `build_personal_report()`（broadcast.py）跟 `build_instant_report()`（webhook.py）三處幾乎一樣的單浪點格式化邏輯重複，未來加欄位要記得改 3 處。可抽成共用 helper，例如 `build_spot_lines(spot_name, data, cfg, profile=None, show_tide=False)`

### 低優先
- [ ] 訂閱開關（用戶自助暫停/恢復）
- [ ] 警戒 de-dup 持久化（目前存在記憶體，Render 重啟後重置，可考慮存 Supabase `alerts_log` 表）
- [x] LINE_CHANNEL_SECRET 金鑰輪替 ✅（2026-06-22 完成，LINE Console 重新產生 + Render/本機 .env 同步更新，傳訊息測試正常）
- [x] CWA_API_KEY 金鑰輪替 ✅（2026-06-22 完成）
- [x] **CWA API 在 Render 上 SSL 連線失敗** ✅（2026-06-22 修復。根因：CWA 證書鏈缺少 Subject Key Identifier 欄位，本機 OpenSSL 不檢查、Render 的 OpenSSL 3.2+ 嚴格模式會直接拒絕，跟金鑰本身無關。試過 `verify=False`、自訂 SSLContext 清嚴格旗標都沒用，最後改用 `subprocess` 呼叫系統 `curl -sk` 取代 `requests` 才解決。詳細踩坑記錄在 line-bot-builder skill 第17條）

### 未來功能（暫緩）
- [ ] 影片連結投稿：浪友傳 `📹 烏石港 https://...`，存 `surf_videos` 表，廣播附「今日影片」

---

## LINE 推播額度

| 方案 | Push 額度 |
|------|----------|
| 免費 | 500 則/月 |

目前約 1 位訂閱者，用量遠低於上限（每日 2 次廣播 × 30 天 + 偶發警戒 ≈ 70 則/月）。超過約 16 位訂閱者時才會逼近上限。

---

## 快速啟動指令

```bash
cd ~/Downloads/melon-agent/surf_robot

# 廣播測試（立即執行）
python3 broadcast.py --now

# 本機 Webhook（需搭配 ngrok）
python3 webhook.py
ngrok http 5000   # 另開視窗

# 後台管理網頁
streamlit run app.py

# Google Sheet 同步測試（需先設好對應環境變數）
python3 sync_to_sheets.py

# 重建並上傳圖文選單（會立即影響所有使用者，上傳前先確認過設計）
python3 setup_richmenu.py
```
