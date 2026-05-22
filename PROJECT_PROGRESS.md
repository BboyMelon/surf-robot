# 🌊 浪況機器人專案進度

## 專案資訊
- **專案名稱**：LINE 浪況自動訂閱與回報機器人
- **專案路徑**：`/Users/melon/Downloads/surf_robot/`
- **最後更新**：2026-05-21

---

## 技術架構

| 元件 | 技術 | 說明 |
|------|------|------|
| 前端網頁 | Python Streamlit | 訂閱表單 + Windy 地圖 |
| 後端 Webhook | Python Flask | LINE 事件接收 |
| 廣播排程 | Python schedule | 每日 05:00 推播（待擴充）|
| 雲端資料庫 | Supabase (PostgreSQL) | members / groups / profiles |
| 浪況資料 | CWA O-B0075-001 | 氣象署海象監測 API |
| 推播 | LINE Messaging API | Push Message + Reply Message |

---

## 金鑰與設定（存於 .env）

| 變數 | 說明 |
|------|------|
| `CWA_API_KEY` | `CWA-548E18F6-09C1-4F44-A924-9E18773BFF4D` |
| `LINE_CHANNEL_ACCESS_TOKEN` | 已設定 |
| `LINE_CHANNEL_SECRET` | `13acce66c3d54a067e2c46afd1d6bf7d` |
| `SUPABASE_URL` | `https://byrzvtpctudqhqfzeyom.supabase.co` |
| `SUPABASE_KEY` | 已設定 |
| `STREAMLIT_URL` | 待部署後填入（目前顯示「尚未部署」）|

---

## 檔案結構

```
surf_robot/
├── .env                    ✅ 所有金鑰（勿上傳 git）
├── .env.example            ✅ 金鑰範本
├── .gitignore              ✅
├── Procfile                ✅ gunicorn webhook:app（Render 部署用）
├── config.py               ✅ 浪點設定、分級邏輯、STREAMLIT_URL
├── db.py                   ✅ Supabase/SQLite 資料庫層
├── app.py                  ✅ Streamlit 訂閱網頁
├── webhook.py              ✅ LINE Webhook 伺服器（含選單觸發、即時查詢）
├── broadcast.py            ✅ 每日廣播 + 個人化推播
├── setup_richmenu.py       ✅ LINE 圖文選單建立腳本
├── richmenu.png            ✅ 選單圖片（已上傳 LINE）
├── requirements.txt        ✅ 含 gunicorn（待加 Pillow）
└── PROJECT_PROGRESS.md     ✅ 本文件
```

---

## Supabase 資料表（全部已建立 ✅）

### members
```sql
id, email, line_id (UNIQUE), status, created_at
```

### groups
```sql
id, group_id (UNIQUE), status, joined_at
```

### profiles
```sql
id, line_id (UNIQUE), gender, surf_years, board_type, fav_spots, updated_at
```
> RLS Policy `allow_all` 已設定，寫入正常 ✅

---

## 浪況資料來源

| API | 用途 | 狀態 |
|-----|------|------|
| CWA `O-B0075-001` | 48小時浮標站即時浪況 | ✅ |
| CWA `F-A0021-001` | 潮汐預報 | ✅ |
| CWA `O-A0003-001` | 氣象站風向 | ✅ |
| NODASS 浮標 API | 國家海洋研究院 | ✅ 免 Token |

---

## 監測浪點（14 個）

### 🔵 北部
- 金山沙珠灣 → `46778A`
- 翡翠灣 → `C6AH2`

### 🟢 宜蘭
- 宜蘭外澳 → `46757B`
- 烏石港 → `46757B`

### 🟡 中部
- 台中松柏港 → `46714D`
- 外埔 → `COMC08`

### 🟠 東部｜花蓮
- 北濱公園 → `46706A`
- 環保公園 → `46706A`

### 🟠 東部｜台東
- 金樽 → `46761F`
- 東河 → `46761F`

### 🔴 南部
- 台南漁光島 → `46699A`
- 恆春南灣 → `46694A`
- 恆春九鵬 → `C6S94`
- 恆春佳樂水 → `46694A`

---

## LINE 圖文選單 ✅（2026-05-21 建立）

| 格 | 名稱 | 觸發文字 | 回應 |
|----|------|---------|------|
| 1 | 🔍 即時浪況查詢 | 點擊後提示輸入浪點 | 引導文字 |
| 2 | 📝 Surfer 檔案建立 | 彈出填表格式 | 表單文字 |
| 3 | 📚 專業海象觀測網 | Flex Message | CWA / NODASS / Swell Eye 連結 |
| 4 | 🗺️ Windy 動態地圖 | 回傳 Streamlit URL | 待部署後更新 |

---

## LINE 指令

| 使用者傳送 | 機器人回應 |
|-----------|-----------|
| 任意浪點名稱（如：烏石港） | 即時浪況資料 |
| 地區名稱（如：北部、宜蘭、東部、南部） | 該地區所有浪點資料 |
| 性別/浪齡/版型/常衝浪點格式 | 建立/更新 Profile |
| 我的資料 | 查詢目前檔案 |
| 我的ID | 回覆 LINE 顯示名稱 |

---

## 已完成功能 ✅（截至 2026-05-21）

- [x] Streamlit 訂閱網頁（Email + LINE ID 表單 + Windy 地圖）
- [x] 管理員後台（密碼：surf123）
- [x] Supabase 三張表（members / groups / profiles）+ RLS 政策
- [x] CWA O-B0075-001 浮標 API 串接（14 浪點）
- [x] Swell Eye 湧浪能量、GoOcean 分級、陸風判斷
- [x] LINE Push 廣播（每日 05:00，排程已可用）
- [x] User Profile 解析 + 個人化廣播（常衝浪點過濾）
- [x] Git 初始化 + .gitignore + Procfile
- [x] 廣播測試成功（推播到真實 LINE ✅）
- [x] ngrok Webhook 部署（Verify 成功 ✅）
- [x] LINE 圖文選單（2×2 格，深藍海洋主題）✅
- [x] 即時浪況查詢（輸入浪點/地區名稱 → 即時 CWA 資料）✅
- [x] 未建檔用戶自動引導填資料 ✅
- [x] 「我的ID」改回傳 LINE 顯示名稱 ✅
- [x] 歡迎訊息更新為黃金浪況預報版文案 ✅

---

## 待辦清單 🔲

### 🔴 高優先
- [x] **Render.com 正式部署** ✅ https://surf-robot.onrender.com
- [x] **GitHub repo 建立** ✅ https://github.com/BboyMelon/surf-robot
- [x] **GitHub Actions keep-alive** ✅ 每 5 分鐘 ping /health
- [x] **🐛 CWA API 被 Render 封鎖** ✅ 已修復
  - 解法：加入 Open-Meteo Marine API 作為 fallback（免費/無 Token/全球可存取）
  - `get_marine_data()` 優先 CWA，失敗自動切換 Open-Meteo
  - webhook + broadcast 全部改用 `get_marine_data()`
  - Open-Meteo 無潮位/水溫，顯示「—」並加備援說明

### 🟡 中優先
- [x] **廣播時段統一**：broadcast.py 改為 05:00，所有文案同步 ✅
- [ ] **requirements.txt 加入 Pillow**（setup_richmenu.py 使用）
- [ ] **長浪警戒即時通知**（週期 > 8s 且浪高 > 1.5m → 立即推播）

### 🟢 低優先
- [ ] Streamlit 雲端部署（Streamlit Cloud 免費）
- [ ] Streamlit 加入 Profile 查詢欄位
- [ ] 「所有浪點」全台總覽指令

---

## 快速啟動指令

```bash
cd ~/Downloads/surf_robot

# Webhook（需搭配 ngrok）
python3 webhook.py

# ngrok 隧道（另開視窗）
ngrok http 5000

# 廣播測試（立即執行）
python3 broadcast.py --now

# 訂閱網頁
streamlit run app.py

# 重建圖文選單（一次性）
python3 setup_richmenu.py
```
