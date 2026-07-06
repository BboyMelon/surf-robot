# 🌊 LINE 浪況機器人 — 系統架構說明

> **適用場景**：專題報告、技術說明、面試展示  
> **最後更新**：2026-07-06  
> **專案連結**：https://github.com/BboyMelon/surf-robot

---

## 1. 專案概述

### 解決的問題
台灣衝浪愛好者每天要從多個政府網站手動查詢浪況，資訊分散、格式不統一、沒有個人化建議。

### 解決方式
打造一個 LINE 聊天機器人，每天**自動**抓取 CWA（中央氣象署）浮標即時資料，轉換成衝浪者看得懂的語言，主動推播給訂閱者，並支援即時查詢互動。

### 核心功能
| 功能 | 說明 |
|------|------|
| 每日推播 | 每天 05:00 / 15:00 推送全台 15 大浪點浪況 |
| 個人化建議 | 依用戶的浪齡/板型/常衝浪點，給出「適合/不適合」判斷 |
| 即時查詢 | 在 LINE 輸入浪點名稱，秒回當前浪況 + 今日潮汐 |
| 長浪警戒 | 偵測到 Ground Swell（大湧浪）自動推播警戒 |
| 颱風通知 | 颱風進入台灣 1000km 範圍自動推播 |
| YouTube 直播 | 一鍵開啟各浪點官方直播連結（北/東/南 共 20 支）|

---

## 2. 整體系統架構圖

```
┌─────────────────────────────────────────────────────────────────┐
│                         外部資料源                               │
│                                                                 │
│  ┌──────────────────┐     ┌──────────────────────────────────┐  │
│  │  CWA O-B0075-001 │     │  Open-Meteo Marine API           │  │
│  │  浮標即時海象     │     │  （全球免費備援，無需 API Key）     │  │
│  │  10 浮標站        │     │  提供波高/週期/風向               │  │
│  └────────┬─────────┘     └──────────────┬───────────────────┘  │
│           │ HTTPS curl                    │ HTTPS requests       │
└───────────┼──────────────────────────────┼─────────────────────┘
            │                              │ (fallback)
            ▼                              ▼
┌───────────────────────────────────────────────────────────────┐
│               Render.com（主伺服器，Free Tier）                  │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  webhook.py  ←── LINE Webhook 事件入口（Flask）           │  │
│  │  ┌──────────────────────────────────────────────────┐   │  │
│  │  │ 主執行緒：接收 → 簽章驗證 → 立即回 200 OK          │   │  │
│  │  │ 背景執行緒：解析事件 → 查資料 → 回覆用戶            │   │  │
│  │  └──────────────────────────────────────────────────┘   │  │
│  │                                                          │  │
│  │  broadcast.py ←── 資料抓取 / 評分 / 廣播邏輯             │  │
│  │  ┌──────────────────────────────────────────────────┐   │  │
│  │  │ get_marine_data()  →  swell_quality_score()       │   │  │
│  │  │ find_best_spots()  →  build_spot_block()          │   │  │
│  │  │ check_swell_alerts() / check_typhoon_alerts()     │   │  │
│  │  └──────────────────────────────────────────────────┘   │  │
│  │                                                          │  │
│  │  line_api.py ←── 統一 LINE API 呼叫層                    │  │
│  │  db.py       ←── Supabase / SQLite 資料層                │  │
│  │  config.py   ←── 浪點設定 / 評分常數 / API 金鑰           │  │
│  └─────────────────────────────────────────────────────────┘  │
└──────────────┬──────────────────────┬─────────────────────────┘
               │ HTTPS                │ HTTPS
               ▼                      ▼
   ┌───────────────────┐   ┌──────────────────────┐
   │  LINE Messaging   │   │  Supabase（PostgreSQL）│
   │  API              │   │  members / groups     │
   │  Push + Reply     │   │  profiles / alerts_log│
   └─────────┬─────────┘   └──────────────────────┘
             │ 推播 / 回覆
             ▼
   ┌─────────────────────┐
   │  用戶 LINE App       │
   │  （收到訊息 / 互動）  │
   └─────────────────────┘


┌───────────────────────────────────────────────────────────────┐
│               GitHub Actions（定時觸發器）                      │
│                                                               │
│  broadcast.yml  ─── 台灣 05:00 + 15:00 觸發廣播端點           │
│  keep_alive.yml ─── 台灣 05:00-10:00 / 14:00-20:00 每 5 分鐘 │
│                     ping /health 避免 Render 進入睡眠          │
│  deploy.yml     ─── push main 自動觸發 Render 重新部署         │
│  sync_sheets.yml─── 台灣 04:30 把 Supabase 資料同步 Google Sheet│
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│               Streamlit Community Cloud（後台管理）             │
│  app.py  → 訂閱名單 / Surfer 檔案 / 手動推播按鈕               │
└───────────────────────────────────────────────────────────────┘
```

---

## 3. 技術選型與理由

| 技術 | 選擇理由 |
|------|---------|
| **Python + Flask** | 輕量 Webhook 伺服器，適合單一 Render Free instance |
| **LINE Messaging API** | 台灣用戶覆蓋率高，支援 Push / Reply / Flex Message / Rich Menu |
| **CWA O-B0075-001** | 台灣官方浮標資料，有即時波高/週期/風向/海溫 |
| **Open-Meteo Marine** | 免費、免 API Key，全球 IP 可用，作為 CWA 備援 |
| **Supabase（PostgreSQL）** | 免費雲端 DB，有 REST API，避免 Render 重啟後資料消失 |
| **GitHub Actions** | 免費定時任務，解決 Render Free Tier 不能可靠執行 cron 的問題 |
| **Render Free Tier** | 免費 Flask 伺服器；缺點是有睡眠機制，需靠 keep-alive 保持活躍 |
| **Gunicorn** | Render 官方推薦的 Python WSGI 伺服器，比 Flask 內建開發伺服器穩定 |

---

## 4. 檔案結構與各模組職責

```
surf_robot/
├── config.py          ← 【設定層】浪點定義、潮汐站對應、評分常數、API 金鑰
├── db.py              ← 【資料層】Supabase/SQLite 讀寫抽象，自動偵測環境切換
├── line_api.py        ← 【API 層】統一 LINE push/reply/profile 呼叫
├── broadcast.py       ← 【核心邏輯】抓資料、評分、組訊息、廣播、警戒
├── webhook.py         ← 【事件層】LINE Webhook 入口、指令處理、背景排程
├── app.py             ← 【後台】Streamlit 管理介面（另外部署）
├── setup_richmenu.py  ← 【工具】LINE 圖文選單圖片生成 + 上傳（手動執行一次）
├── sync_to_sheets.py  ← 【工具】Supabase → Google Sheet 同步（GitHub Actions 跑）
├── Procfile           ← Render 啟動指令：gunicorn webhook:app
└── .github/workflows/ ← 4 個 GitHub Actions 工作流程
    ├── deploy.yml
    ├── keep_alive.yml
    ├── broadcast.yml
    └── sync_sheets.yml
```

### 模組依賴關係

```
webhook.py
  ├── broadcast.py  (get_marine_data, build_spot_block, ...)
  ├── line_api.py   (push_text, reply_text, reply_flex)
  ├── db.py         (add_member, get_profile, ...)
  └── config.py     (LINE_CHANNEL_SECRET, SURF_SPOTS_CONFIG, ...)

broadcast.py
  ├── line_api.py   (push_text)
  ├── db.py         (get_all_members, log_alert, ...)
  └── config.py     (get_surf_level, SURF_SPOTS_CONFIG, ...)
```

---

## 5. 資料來源說明

### 5-1 CWA O-B0075-001（主要浮標資料）

- **來源**：中央氣象署開放資料平台（需申請免費 API Key）
- **資料內容**：台灣周邊 10 個浮標站的即時觀測值
- **更新頻率**：每小時更新，但有時整批卡住（颱風期間可能 48 小時未更新）
- **特殊問題**：Render 容器內的 OpenSSL 版本較新，會拒絕 CWA 的 HTTPS 憑證（Missing Subject Key Identifier），解決方式是改用系統 `curl` 子行程取代 Python `requests`

```python
# 解決 CWA SSL 憑證問題的關鍵程式碼
result = subprocess.run(
    ["curl", "-sk", url],  # -k 跳過嚴格驗證，-s 不顯示進度
    capture_output=True, text=True, timeout=timeout
)
```

### 5-2 Open-Meteo Marine API（備援資料）

- **來源**：歐洲開源氣象模型（不需 API Key）
- **資料內容**：逐小時波高、波浪週期、波浪方向、風速風向（無海溫、無潮位）
- **觸發時機**：CWA 全部失效 → 完全切換；CWA 部分缺站 → 針對缺失站補充

```python
# 混合資料策略（broadcast.py get_marine_data()）
def get_marine_data() -> dict:
    cwa_data = fetch_marine_data()
    if not cwa_data:                         # CWA 全部失效
        return fetch_marine_data_openmeteo()
    missing = STATION_COORDS.keys() - cwa_data.keys()
    if missing:                               # CWA 部分缺站
        om = fetch_marine_data_openmeteo()
        for sid in missing:
            if sid in om:
                cwa_data[sid] = om[sid]       # 補充缺失站
    return cwa_data
```

### 5-3 資料新鮮度檢查

新增 `MARINE_DATA_MAX_AGE_HOURS = 3`，超過 3 小時的觀測值視同無效，觸發備援：

```python
age_hours = (datetime.now(TW_TZ) - obs_time).total_seconds() / 3600
if age_hours > MARINE_DATA_MAX_AGE_HOURS or wave_sensor_down:
    continue  # 略過此站，讓備援填補
```

**背景說明**：颱風期間 CWA 資料可能卡住，若不檢查新鮮度，機器人會把颱風前 48 小時的平靜資料（0.3m 🟢）誤報為當前狀況，嚴重誤導衝浪者安全判斷。

---

## 6. 浪況評分邏輯

這是整個系統的核心，決定每個浪點「幾顆星」以及「最佳浪點」排名。

### 6-1 GoOcean 安全分級（config.py）

對應國家海洋研究院 GoOcean 官方標準，以浪高為主判斷，長週期湧浪另外升一級：

```python
def get_surf_level(wave_height, wave_period):
    if wave_height >= 3.0 or (wave_height >= 2.0 and wave_period >= 12):
        return ⛔ 危險封閉
    if wave_height >= 1.8 or (wave_height >= 1.0 and wave_period >= 12):
        return 🔴 進階 Expert
    if wave_height >= 0.8 or (wave_height >= 0.5 and wave_period >= 9):
        return 🟡 中階 Intermediate
    return 🟢 初學 Primary
```

**設計原因**：同樣 1.0m 的浪，週期 12s（Ground Swell）的能量和衝擊力遠大於週期 5s（Wind Swell），對安全影響截然不同。

### 6-2 品質分數計算（broadcast.py）

```
品質分數 = 浪高(m) × 週期(s) × 週期品質係數

週期品質係數：
  < 7s  → 0.7  （短週期風浪，雜亂打板）
  7-9s  → 1.0  （一般）
  9-12s → 1.3  （長週期混合浪）
  ≥ 12s → 1.6  （Ground Swell，乾淨有力）
```

**例子**：
- 1.0m × 6s（風浪）：1.0 × 6 × 0.7 = **4.2 分**（⭐⭐）
- 1.0m × 12s（湧浪）：1.0 × 12 × 1.6 = **19.2 分**（⭐⭐⭐⭐⭐）
- 相同浪高但評分差距 4.6 倍，反映衝浪體驗的真實差異

### 6-3 星數計算

```python
score = swell_quality_score(wave_h, period)
星數門檻：< 3 → ⭐；< 5 → ⭐⭐；< 10 → ⭐⭐⭐；< 18 → ⭐⭐⭐⭐；≥ 18 → ⭐⭐⭐⭐⭐
陸風加成：若今日吹陸風（離岸風），分數 × 1.3，最多加到滿分
```

**陸風（Offshore Wind）說明**：陸風從陸地吹向海面，可以把浪形「梳理」成乾淨立牆，是衝浪界最喜歡的風況。每個浪點有不同的陸風方向（在 `config.py` 定義），例如：翡翠灣的陸風是東南/南風，恆春南灣的陸風是北/東北風。

### 6-4 最佳浪點排序（find_best_spots）

```
排序鍵 = swell_quality_score(wave_h, period) × (1.3 if offshore else 1.0)
取前 3 名，同浮標站只取最高分的一個代表浪點
```

---

## 7. LINE 整合機制

### 7-1 Webhook 事件處理流程

```
用戶傳訊息 / 點按鈕
      ↓
LINE 伺服器 POST https://surf-robot.onrender.com/webhook
      ↓
Flask 路由 webhook()
  1. 驗證簽章（HMAC-SHA256，防假冒）
  2. 立即回 HTTP 200（LINE 要求 < 1 秒）
  3. 把 events 丟進背景執行緒
      ↓ (背景)
_process_events(events)
  ├── 解析 event_type / msg_text / user_id
  ├── 查 Supabase 取用戶 Profile
  └── 依指令回覆：reply_text / reply_flex
        ↓ 失敗時（reply_token 過期）
        改用 push_message 補送（fallback）
```

**為什麼要非同步？** 查詢浪況需要呼叫 CWA/Open-Meteo API，可能耗時 2-8 秒。若同步等待再回 200，LINE 會認為 Webhook 失敗而重送相同事件，造成重複推播或重複建檔。

### 7-2 圖文選單（Rich Menu）

圖文選單的圖片用 **Python Pillow** 直接繪製，按鈕的點擊區域則透過 LINE API 的 `areas` 座標定義：

```
圖片（2500×843 px）= 視覺皮層，用 PIL 畫漸層 + emoji + 文字
按鈕行為             = areas 座標對應文字觸發（type: "message"）

點擊左下格 → LINE 幫用戶發出 "📺 浪況數據與直播資源"
           → Webhook 收到 → 回傳 Flex Carousel
```

```python
# setup_richmenu.py 核心邏輯
make_image()        # Pillow 畫圖 → richmenu.png
create_richmenu()   # POST /v2/bot/richmenu （定義 areas + 觸發文字）
upload_image()      # POST richmenu/{id}/content （上傳圖片）
set_default()       # POST user/all/richmenu/{id} （設為全用戶預設）
```

### 7-3 Flex Message（互動卡片）

比純文字更豐富的訊息格式，支援按鈕、圖文混排、Carousel（多張滑動卡片）：

```
浪況數據與直播資源 → Flex Carousel（可左右滑動）
  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
  │ 📊 海象觀測  │ │ 🔴 北部直播  │ │ 🔴 東部直播  │ │ 🔴 南部直播  │
  │ CWA 按鈕    │ │ 7 個 YouTube│ │ 4 個 YouTube│ │ 5 個 YouTube│
  │ NODASS 按鈕 │ │ 連結按鈕    │ │ 連結按鈕    │ │ 連結按鈕    │
  │ Swell Eye  │ │             │ │             │ │             │
  │ Windy      │ │             │ │             │ │             │
  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
```

---

## 8. 推播排程設計

### 問題：Render Free Tier 的睡眠機制

Render 免費方案的服務在 **15 分鐘無請求** 後會進入睡眠，再次喚醒需要 30-60 秒冷啟動時間。這導致：
- 定時廣播到時沒人打 /health，服務還在睡眠 → 廣播失敗
- 用戶傳訊息時需等 30-60 秒才有回應

### 解法：GitHub Actions 分擔排程任務

```
Render 背景執行緒 (schedule)
  ├── check_swell_alerts()   ← 每 3 小時執行（只在服務醒著時）
  └── check_typhoon_alerts() ← 每 1 小時執行（只在服務醒著時）

GitHub Actions（外部定時器，可靠）
  ├── broadcast.yml          ← 每天台灣 05:00 + 15:00
  │   先 curl /health 確認服務醒著（最多等 2 分鐘）
  │   再 POST /broadcast-now 觸發廣播
  │
  └── keep_alive.yml         ← 台灣 05:00-10:00 + 14:00-20:00，每 5 分鐘
      ping /health 讓 Render 保持清醒
      （只在廣播前後的高峰時段才開啟，其他時間讓它睡，節省免費額度）
```

### 廣播流程（broadcast.yml → Render → LINE）

```
GitHub Actions 定時觸發
      ↓
curl /health（輪詢等服務醒來）
      ↓
POST /broadcast-now（附 Authorization: Bearer BROADCAST_TOKEN）
      ↓
broadcast() 函式執行
  1. get_marine_data()        取浮標資料（含備援邏輯）
  2. fetch_tomorrow_forecast() 取明日預報（Open-Meteo 7 天模型）
  3. find_best_spots()         計算今日最佳前 3 名
  4. build_report()            組通用廣播文字
  5. get_all_members() + get_all_profiles() 一次性批次查 DB
  6. 個人用戶：build_personal_report() → push_text() 推送
  7. 群組：push 通用版
```

---

## 9. 資料庫設計（Supabase PostgreSQL）

```sql
-- 個人訂閱者
members (
  line_id    TEXT UNIQUE,   -- LINE User ID（以 U 開頭）
  email      TEXT,
  status     TEXT,          -- 'active' / 'paused' / 'inactive'
  created_at TIMESTAMP
)

-- 群組訂閱
groups (
  group_id   TEXT UNIQUE,   -- LINE Group ID（以 C 開頭）
  status     TEXT,
  joined_at  TIMESTAMP
)

-- 衝浪者個人檔案
profiles (
  line_id      TEXT UNIQUE,
  nickname     TEXT,         -- 自填暱稱
  display_name TEXT,         -- 從 LINE API 自動抓取的顯示名稱
  gender       TEXT,
  surf_years   INTEGER,      -- 浪齡（年）
  board_type   TEXT,         -- 長板 / 短板 / 中長板
  fav_spots    TEXT,         -- 常衝浪點（逗號分隔）
  updated_at   TIMESTAMP
)

-- 警戒推播紀錄（防重複推播）
alerts_log (
  alert_type TEXT,           -- 'swell' / 'typhoon'
  alert_key  TEXT UNIQUE,    -- 颱風 ID 或浪點名稱
  created_at TIMESTAMP
)
```

**為什麼需要 `alerts_log`？**  
Render 重啟時 in-memory 變數會歸零，如果用 Python dict 記錄「這個颱風已推過」，重啟後就忘了，導致同一個颱風被推播多次。改用 DB 儲存確保推播狀態在重啟後仍然保留。

---

## 10. 容錯機制設計

| 場景 | 容錯做法 |
|------|---------|
| CWA API SSL 憑證問題 | 改用系統 `curl -sk` 子行程，繞過 Python OpenSSL 的嚴格驗證 |
| CWA API 偶發失敗 | `_cwa_get()` 重試 3 次，每次間隔 2 秒 |
| CWA 資料超過 3 小時未更新 | 略過過期站，觸發 Open-Meteo 備援補充 |
| CWA 感測器離線（回傳 "None"） | `wave_sensor_down` 偵測，同樣觸發備援 |
| CWA 全部站失效 | 完全切換到 Open-Meteo |
| Render 部署重啟時 reply_token 過期 | `reply_message()` 失敗 → 自動改 `push_message()` 補送 |
| LINE Webhook 超時 | 先回 200，事件丟背景執行緒處理（非同步） |
| Supabase 查詢失敗 | try/except 回傳 None，不中斷主流程 |
| 個別 event 處理崩潰 | `_process_events()` for 迴圈每個 event 獨立 try/except |
| Render 睡眠導致廣播失敗 | GitHub Actions broadcast.yml 先輪詢 /health 確認服務醒著再觸發 |

---

## 11. 安全性設計

| 項目 | 做法 |
|------|------|
| LINE Webhook 防偽造 | 驗證 `X-Line-Signature`（HMAC-SHA256） |
| 廣播端點 `/broadcast-now` 防濫用 | 需附 `Authorization: Bearer BROADCAST_TOKEN` |
| 所有 API 金鑰 | 存於 `.env`（本機）+ Render 環境變數 + GitHub Secrets，**不進 git** |
| Streamlit 後台 | 需輸入管理員密碼才能看到訂閱名單 + 推播按鈕 |

---

## 12. 本機開發快速啟動

```bash
# 安裝依賴
pip install -r requirements.txt

# 設定金鑰（複製 .env.example → .env，填入各 API Key）
cp .env.example .env

# 測試廣播（不推播給真實用戶，只印出結果）
python3 broadcast.py --now

# 啟動 Webhook（需搭配 ngrok 或類似工具轉接 LINE）
python3 webhook.py
# 另開視窗：ngrok http 5000

# 後台管理介面
streamlit run app.py

# 重建並上傳圖文選單（會立即影響所有用戶，上傳前先確認設計）
python3 setup_richmenu.py
```

---

## 13. 關鍵技術決策回顧

| 決策 | 選擇 | 棄選 | 原因 |
|------|------|------|------|
| 排程方式 | GitHub Actions | Render Cron（付費）或 APScheduler | Free Tier 不能保證服務醒著，GitHub Actions 作為外部可靠觸發器更穩定 |
| SSL 問題 | subprocess curl | requests + verify=False | 問題發生在 Python ssl 模組底層，requests 層的設定無法觸及 |
| 非同步 Webhook | 背景執行緒 | 同步等待 | 外部 API 呼叫可能超時，LINE 會重送事件造成重複處理 |
| 浮標資料備援 | Open-Meteo | 只用 CWA | CWA 颱風期間整批卡住，需要可靠的全天候備援 |
| 資料庫 | Supabase | SQLite | Render 每次重啟 ephemeral storage 都會重置，需要雲端持久化 |

---

*文件由 Claude Code 協助生成，基於 `broadcast.py`、`webhook.py`、`config.py`、`db.py`、`line_api.py` 原始碼整理。*
