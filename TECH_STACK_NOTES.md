# 🧭 我的技術棧筆記：LINE 浪況機器人 + 浪誌 TIDELOG 部落格

> 這份文件不是給別人看的架構圖（那份是 `ARCHITECTURE.md`），是寫給**我自己**看的：
> 弄懂「我到底用了什麼技術、為什麼要這樣做、跟我熟悉的 VB / GAS 怎麼對應」。
> 最後更新：2026-07-30

---

## 1. 兩個專案的關係

```
surf-robot（LINE 機器人，主專案）
  └── 跑在 Render.com（會執行 Python 程式的伺服器）
  └── 資料庫：Supabase（雲端 PostgreSQL）
  └── 對外提供 2 個公開 API 給浪誌網站用：
        /api/live-conditions  → 給浪點地圖抓即時浪況
        /api/contact          → 給聯絡我們表單寫資料

tidelog-site（浪誌 TIDELOG 部落格，獨立 repo，放在 surf_robot/tidelog-site/ 資料夾裡）
  └── 跑在 GitHub Pages（只能放純網頁，不能跑 Python）
  └── 沒有自己的資料庫，需要存資料 or 抓即時資料時，改打 surf-robot 的 API
```

一句話理解兩者差異：**surf-robot 是「會執行程式」的後端，tidelog-site 是「純展示」的前端**，兩者用 HTTP API 串起來，就像 GAS 的 Web App（`doGet`/`doPost`）跟前端網頁的關係一樣。

---

## 2. Git + 網頁部署，到底怎麼「上線」的？

這是兩種完全不同的部署模式，搞懂差異之後你會發現原理其實不複雜：

### 模式 A：純靜態網站（tidelog-site）→ GitHub Pages

```
本機改檔案 → git add/commit/push → GitHub 偵測到 main branch 有更新
           → GitHub Pages 自動重新產生網站（不用你做任何事）
```

GitHub Pages 的角色只是「檔案伺服器」，你 push 什麼 `.html`/`.css`/`.js`/圖片檔上去，它就原封不動地把這些檔案透過網址發佈出去。**沒有任何程式在「執行」**，純粹是檔案搬運。這是為什麼 tidelog-site 不能有 Python 後端邏輯的原因。

### 模式 B：會執行程式的網站（surf-robot）→ Render.com

```
本機改 webhook.py/broadcast.py 等
  → git push
  → GitHub Actions 的 deploy.yml 被觸發
  → deploy.yml 呼叫 Render 的「Deploy Hook」網址（一個特殊 URL）
  → Render 收到通知 → 重新拉取 repo → 重新啟動 Python 程式（gunicorn webhook:app）
```

這裡多了一層，因為 Render 要**真的執行** `webhook.py` 這支程式（背景一直開著監聽 LINE 傳來的訊息），不是單純發佈檔案。`deploy.yml` 就是「push 完之後自動去按 Render 的重新部署按鈕」的機器人。

**VB 對照**：模式 A 像是把寫好的 `.exe` 直接丟到共用資料夾給人執行；模式 B 更像是你有一台永遠開著的電腦，改完程式碼要重新編譯、重新啟動這支背景程式。

---

## 3. LINE 機器人（surf-robot）檔案與函數地圖

### 3-1 檔案職責一覽

| 檔案 | 職責 | VB/GAS 對照 |
|---|---|---|
| `config.py` | 存放浪點清單、API 金鑰、評分門檻等「設定值」 | 像 GAS 的 `Config` 常數表，或 VB 的 `Module` 放全域常數 |
| `db.py` | 統一處理讀寫 Supabase（或本機 SQLite）的所有函數 | 像 VB 的資料存取層（DAL），呼叫端不用管底層是 SQL Server 還是 Access |
| `line_api.py` | 統一封裝呼叫 LINE 官方 API（傳訊息、查大頭貼名稱） | 像自己包一個 `LineHelper` 類別，所有人共用同一套呼叫邏輯 |
| `broadcast.py` | 核心運算邏輯：抓浮標資料、算星等、組廣播文字、推播 | 這是整個系統的「大腦」，最多函數都在這裡 |
| `webhook.py` | LINE 訊息進來的入口，處理指令、跑排程、對外提供 API 端點 | 像 GAS 的 `doPost(e)`，是外部請求打進來的第一個接觸點 |
| `app.py` | Streamlit 後台管理頁面（另外部署，跟主程式分開跑） | 像一個簡易版的 Access 表單，給你自己看資料用 |
| `setup_richmenu.py` | 手動執行一次，畫圖文選單圖片 + 上傳到 LINE | 工具腳本，不是常駐程式 |

### 3-2 資料怎麼流動（一次廣播的完整路徑）

```
GitHub Actions broadcast.yml（台灣 05:00 觸發）
  → POST /broadcast-now（webhook.py 的路由）
    → 開一個背景執行緒跑 broadcast.py 的 broadcast() 函式
       1. get_marine_data()          抓 CWA 浮標資料（失敗就切 Open-Meteo 備援）
       2. fetch_tomorrow_forecast()  抓明日預報
       3. find_best_spots()          算出今日最佳前 3 名浪點
       4. build_report() / build_personal_report()  組出文字訊息
       5. get_broadcast_members()    從 Supabase 撈「已完成表單」的訂閱者名單
       6. push_text()（line_api.py） 一個個推播出去
       7. log_alert("broadcast_success", 今日日期)   寫進 Supabase 當作「今天推過了」的紀錄
```

### 3-3 「物件」是什麼？（Python 的資料結構，對應 VB 的 Type/GAS 的物件）

Python 沒有 VB 那種 `Type`/`Structure`，這個專案主要用 **dict（字典）** 當作簡易物件在用，例如 `config.py`：

```python
SURF_SPOTS_CONFIG = {
    "烏石港": {
        "category": "🔵 北部",
        "offshore_wind": ["西", "西南", "南"],
        "safety_note": "防波堤北側礁岩區，注意退流",
    },
    ...
}
```

這概念上等同 GAS 裡用 `{}` 存一筆資料，或 VB 用 `Type SpotInfo` 定義欄位再宣告變數——都是「把相關的欄位包成一包」，Python 用 dict 是因為彈性大、寫起來快，缺點是沒有強型別檢查（打錯欄位名稱不會在編譯期被抓到，這是跟 VB 最大的差異，也是為什麼這個專案常常因為「欄位名稱打錯/忘記加」出過 bug）。

---

## 4. 部落格（tidelog-site）檔案與函數地圖

### 4-1 核心概念：`gen_site.py` 是一支「網頁產生器」

這是整個部落格最重要的觀念：**你平常看到的 `index.html`、`contact.html` 這些檔案都不是手寫的，是跑 `python3 scripts/gen_site.py` 產生出來的。**

```
scripts/gen_site.py（原始碼，你改這個）
  │
  │  裡面定義了：
  │  - MAP_SPOTS / RESOURCE_LINKS / LIVESTREAMS  ← 資料（dict / list）
  │  - nav() / footer() / head()                  ← 共用元件（每頁都會呼叫）
  │  - feat_card() / article_detail()             ← 產生單張卡片/單篇文章 HTML 的函數
  │
  ▼ 執行 python3 scripts/gen_site.py
  │
  ▼
index.html / articles.html / articles/*.html / contact.html / subscribe.html
（這些是「輸出結果」，重新跑一次就會整批覆蓋更新）
```

**為什麼要這樣設計？** 因為 `nav()`（導覽列）在每一頁都長一樣，如果 6 個 `.html` 檔案各自手寫一份導覽列，改一個連結要改 6 次還容易漏改（這個部落格之前就真的發生過導覽列跟 footer 連結對不起來的 bug）。用一個 Python 函數產生，改一次全站同步。

**GAS 對照**：這概念很像用 GAS 的 `HtmlService.createTemplateFromFile()` 搭配範本語法，把共用的 header/footer 抽出來，只是這裡用 Python f-string 手刻字串模板，沒有用到框架。

### 4-2 首頁「浪點地圖」是怎麼畫出來的？

這是這次剛做的功能，技術棧是：

```
Leaflet.js（開源 JS 地圖繪圖套件，免費、不用 API Key）
  + CartoDB Voyager（地圖底圖圖磚來源，這次改成比較像 Google Maps 的配色）
  + OpenStreetMap（底圖的地理資料來源，Leaflet 透過 CartoDB 間接使用）
  + 純 JavaScript fetch()（瀏覽器內建，向 surf-robot 的 /api/live-conditions 要即時浪況資料）
```

運作流程：

```html
<div id="spot-map"></div>   <!-- 地圖要畫在這個空 div 裡 -->

<script>
  const map = L.map("spot-map").setView([23.6, 120.9], 7.4);   // 建地圖，設定台灣中心點+縮放等級
  L.tileLayer("https://...cartocdn.com/rastertiles/voyager/...").addTo(map);  // 貼上底圖圖磚

  FALLBACK_SPOTS.forEach(spot => {
    L.marker([spot.lat, spot.lon]).addTo(map);   // 15 個浪點，各自的經緯度畫一個圖釘
  });

  fetch(LIVE_API_URL)          // 打去 surf-robot 要即時浪況
    .then(res => res.json())
    .then(data => { /* 把每個浪點的浪高/風向/分級寫進對應圖釘的彈出視窗 */ });
</script>
```

**關鍵理解**：地圖本身（台灣的形狀、道路、城市名稱）是 CartoDB/OpenStreetMap 提供的圖磚（一格一格的圖片，你滑動地圖時瀏覽器動態下載對應格子），**不是你自己畫的**；你自己做的是「在這張現成地圖上，標記 15 個點 + 讓點擊圖釘能顯示即時資料」這件事，這也是為什麼不用申請 Google Maps API Key（那個要綁信用卡），Leaflet+CartoDB 這組合完全免費。

### 4-3 檔案結構

| 位置 | 內容 |
|---|---|
| `scripts/gen_site.py` | 唯一的原始碼，所有文字/資料/邏輯都在這 |
| `css/styles.css` | 全站樣式（手寫 CSS，沒用 Bootstrap/Tailwind 這類框架） |
| `images/` `videos/` | 靜態素材，`gen_site.py` 裡用相對路徑引用 |
| `index.html` 等 | **產生出來的檔案**，不要手改 |
| `README.md` | 給你自己看的操作教學（怎麼新增文章、怎麼上傳 GitHub） |

---

## 5. 每日 05:00 推播「防中斷」機制（完整版）

這是整個系統裡最多層容錯的部分，因為要解決兩個各自獨立的問題：

**問題 1**：Render 免費方案，15 分鐘沒人访問就會睡著，睡著時觸發廣播會失敗
**問題 2**：GitHub Actions 的排程（`schedule: cron`）是 *best-effort*，官方不保證準時，常常延遲 30-60 分鐘才觸發

### 5-1 三層防護，缺一不可

```
第 1 層：cron-job.org（外部、精準排程，非 GitHub Actions）
  ├─ 任務名稱：Surf Robot Keep Alive
  ├─ 打的網址：https://surf-robot.onrender.com/health
  ├─ 排程：*/5 5-9,14-19 * * *（Asia/Taipei 時區，每天 05-09 點、14-19 點，每 5 分鐘）
  └─ 目的：cron-job.org 是專門做定時任務的服務，排程準時度遠比 GitHub Actions 可靠，
           確保 Render 在 05:00 廣播「即將觸發」的關�键窗口內，服務是醒著的，
           不用等 30-60 秒冷啟動

第 2 層：GitHub Actions keep_alive.yml（同樣目的，當 cron-job.org 的備援）
  ├─ 排程：*/5 21,22,23,0,1,6,7,8,9,10,11 * * *（UTC，對應台灣同樣的尖峰時段）
  └─ 跟 cron-job.org 做同一件事，兩邊同時存在等於雙重保險
       （即使其中一個服務出狀況，另一個還在運作）

第 3 層：GitHub Actions broadcast.yml（真正觸發廣播的那一支）
  ├─ 排程：0 21 * * *（UTC 21:00 = 台灣 05:00）
  ├─ 觸發後：先自己 curl /health 輪詢最多 2 分鐘確認服務醒著
  ├─ 再 POST /broadcast-now（帶 Authorization Token 驗證身份）
  └─ 失敗會自動重試 3 次

第 4 層：GitHub Actions broadcast_retry.yml（最後一道保險，06:30 執行）
  ├─ 呼叫 /broadcast-status 查「今天是否已經成功推播過」
  │   （這個狀態存在 Supabase 的 alerts_log 表，記錄 broadcast_success + 今日日期）
  └─ 如果查到還沒成功 → 自動再補打一次 /broadcast-now
```

### 5-2 為什麼要疊這麼多層？各自解決什麼問題

| 層 | 解決的問題 |
|---|---|
| cron-job.org keep-alive | GitHub Actions 排程延遲，用一個「真的準時」的外部服務頂住尖峰時段保活 |
| GitHub Actions keep_alive.yml | cron-job.org 萬一掛掉/額度用完的備援，兩邊互為備份 |
| broadcast.yml 的健康檢查輪詢 | 就算 cron-job.org 跟 keep_alive.yml 都沒接住，觸發廣播前自己再等一次 |
| broadcast.yml 的 3 次重試 | 觸發當下網路瞬斷這種偶發狀況 |
| broadcast_retry.yml + alerts_log | 前面全部都失敗的最終防線，06:30 再檢查一次補推 |

**這個機制是怎麼演化出來的**（踩過的坑）：
1. 一開始只有 GitHub Actions 排程，發現常態性延遲 30-60 分鐘
2. 後來發現 Render 免費方案睡眠導致廣播失敗，加了 keep_alive.yml
3. keep_alive.yml 本身也是 GitHub Actions schedule，一樣有 best-effort 延遲問題 → 這次補上 cron-job.org 這個真正準時的外部服務
4. 曾經因為 Supabase 的 `alerts_log` 表被 RLS（Row Level Security）擋住寫入，導致 `/broadcast-status` 永遠查不到「今天已推播」，讓 `broadcast_retry.yml` 誤判重複推播兩次——後來修好 RLS 設定才解決

**VB/GAS 對照**：這整套很像你在 Windows 工作排程器設一個任務，但你不完全信任它會準時執行，所以又另外用 Task Scheduler 加一個備援任務，再寫一段程式碼「如果 8 點還沒收到執行完成的記錄，就自己再跑一次」——本質上是同一種「不信任單一排程來源」的保守設計。

---

## 6. 資料庫設計（Supabase / PostgreSQL）

| 表 | 用途 | 誰在寫/讀 |
|---|---|---|
| `members` | LINE 個人訂閱者名單，`form_completed` 欄位決定收不收得到 05:00 推播 | webhook.py / broadcast.py |
| `groups` | LINE 群組訂閱名單 | webhook.py / broadcast.py |
| `profiles` | Surfer 個人檔案（浪齡/板型/常去浪點） | webhook.py |
| `alerts_log` | 警戒 + 廣播成功的「已推播記錄」，防止重複推播 | broadcast.py / webhook.py（`/broadcast-status`） |
| `contact_messages` | 浪誌網站聯絡表單訊息 | surf-robot 的 `/api/contact` 端點寫入，Streamlit 後台讀取 |

**為什麼要用雲端資料庫而不是本機檔案？** Render 每次重新部署/重啟，容器裡的檔案系統會整個重置（ephemeral storage）。如果用 SQLite 存在本機檔案，每次重啟資料就消失。Supabase 是獨立於 Render 的雲端服務，資料才能真正持久保存。

---

## 7. 技術對標總表（給你自己複習用）

| 這個專案用的技術 | 概念上等同你熟悉的 |
|---|---|
| Python dict / list | VB `Type`/陣列，GAS 的物件字面量 `{}` |
| Flask 路由（`@app.route`） | GAS 的 `doGet(e)` / `doPost(e)` |
| Supabase（PostgreSQL + REST API） | 一個雲端版、有網址可以打 API 的 Access/SQL Server |
| GitHub Actions `schedule` | Windows工作排程器 / GAS 的觸發器（時間驅動） |
| cron-job.org | 更準時版的觸發器（因為 GAS/GitHub Actions 這類免費排程都有「不保證準時」的先天限制）|
| Leaflet.js + 圖磚服務 | 不用 Google Maps API Key 就能畫地圖的免費替代方案 |
| `gen_site.py` 產生 `.html` | GAS 的 HtmlService 樣板，或 VB 用字串組 HTML 郵件內文的邏輯 |
| GitHub Pages | 把資料夾直接發佈成網站，不用自己架伺服器 |
| Render.com | 一台 24 小時開著（但免費版會睡覺）執行 Python 的遠端電腦 |

---

*這份文件基於 2026-07-30 的實際程式碼與 cron-job.org 設定整理，之後架構有大改記得回來更新。*
