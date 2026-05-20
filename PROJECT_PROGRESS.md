# 🌊 浪況機器人專案進度

## 專案資訊
- **專案名稱**：LINE 浪況自動訂閱與回報機器人
- **專案路徑**：`/Users/melon/Downloads/surf_robot/`
- **最後更新**：2026-05-20

---

## 技術架構

| 元件 | 技術 | 說明 |
|------|------|------|
| 前端網頁 | Python Streamlit | 訂閱表單 + Windy 地圖 |
| 後端 Webhook | Python Flask | LINE 事件接收 |
| 廣播排程 | Python schedule | 每日 06:00 推播 |
| 雲端資料庫 | Supabase (PostgreSQL) | members / groups / profiles |
| 浪況資料 | CWA O-B0075-001 | 氣象署海象監測 API |
| 推播 | LINE Messaging API | Push Message |

---

## 金鑰與設定（存於 .env）

| 變數 | 說明 |
|------|------|
| `CWA_API_KEY` | 中央氣象署 API 金鑰 |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Bot 推播金鑰 |
| `LINE_CHANNEL_SECRET` | LINE Webhook 驗證密鑰 |
| `SUPABASE_URL` | Supabase 專案 URL |
| `SUPABASE_KEY` | Supabase anon key |

---

## 檔案結構

```
surf_robot/
├── .env                    ✅ 所有金鑰（勿上傳 git）
├── .env.example            ✅ 金鑰範本
├── config.py               ✅ 浪點設定、分級邏輯
├── db.py                   ✅ Supabase/SQLite 資料庫層
├── app.py                  ✅ Streamlit 訂閱網頁
├── webhook.py              ✅ LINE Webhook 伺服器
├── broadcast.py            ✅ 每日廣播排程
├── requirements.txt        ✅ 套件清單
└── PROJECT_PROGRESS.md     ✅ 本文件
```

---

## Supabase 資料表

### members（個人訂閱）
```sql
id, email, line_id (UNIQUE), status, created_at
```

### groups（群組訂閱）
```sql
id, group_id (UNIQUE), status, joined_at
```

### profiles（使用者畫像）⚠️ 需確認是否已建立
```sql
id, line_id (UNIQUE), gender, surf_years, board_type, fav_spots, updated_at
```
> **待辦**：確認 profiles 表已在 Supabase 建立

---

## 浪況資料來源

| API | 用途 | 狀態 |
|-----|------|------|
| CWA `O-B0075-001` | 48小時浮標站即時浪況 | ✅ 已驗證可用 |
| CWA `F-A0021-001` | 潮汐預報（備用） | ✅ |
| CWA `O-A0003-001` | 氣象站風向（備用） | ✅ |
| NODASS 浮標 API | 國家海洋研究院即時觀測 | ✅ 免 Token |

---

## 監測浪點（14 個）

### 🔵 北部
- 金山沙珠灣 → 浮標 `46778A`
- 翡翠灣 → 浮標 `C6AH2`

### 🟢 宜蘭
- 宜蘭外澳 → 浮標 `46757B`
- 烏石港 → 浮標 `46757B`（共用）

### 🟡 中部
- 台中松柏港 → 浮標 `46714D`
- 外埔 → 浮標 `COMC08`

### 🟠 東部｜花蓮
- 北濱公園 → 浮標 `46706A`
- 環保公園 → 浮標 `46706A`（共用）

### 🟠 東部｜台東
- 金樽 → 浮標 `46761F`（成功浮標）
- 東河 → 浮標 `46761F`（共用）

### 🔴 南部
- 台南漁光島 → 浮標 `46699A`
- 恆春南灣 → 浮標 `46694A`
- 恆春九鵬 → 浮標 `C6S94`
- 恆春佳樂水 → 浮標 `46694A`（共用）

---

## User Profile 個人化系統

### 技術等級分類
| 浪齡 | 等級 | 安全浪高上限 | 廣播評語風格 |
|------|------|------------|------------|
| 0–1 年 | 🌱 新手 | 1.2m | 安全警告優先 |
| 2–4 年 | 🏄 中級 | 2.5m | 鼓勵出發 |
| 5 年+ | 🔥 進階 | 5.0m | 熱血推坑 |

### LINE 指令
| 指令 | 功能 |
|------|------|
| 填寫性別/浪齡/板型/常衝浪點格式 | 建立/更新個人檔案 |
| 我的資料 | 查詢目前檔案 |
| 我的ID | 回覆 LINE User ID |

---

## 已完成功能 ✅

- [x] Streamlit 訂閱網頁（Email + LINE ID 表單）
- [x] Windy 即時浪高地圖嵌入
- [x] 管理員後台（密碼：surf123）
- [x] Supabase members / groups 資料庫
- [x] CWA O-B0075-001 浮標 API 串接
- [x] 14 個浪點設定（含陸風判斷）
- [x] Swell Eye 湧浪能量計算
- [x] GoOcean 官方衝浪分級
- [x] LINE Push 廣播（每日 06:00）
- [x] User Profile 解析 + 個人化廣播
- [x] 地區分類標題（北部/宜蘭/中部/東部/南部）

---

## 待辦事項 🔲

- [ ] **Supabase profiles 表建立**（需在 SQL Editor 執行）
- [ ] **LINE Webhook 部署**（Render / Railway / ngrok）
  - 部署後需在 LINE Developers 設定 Webhook URL
  - 格式：`https://你的網址/webhook`
- [ ] **測試完整 Profile 流程**（加好友 → 填資料 → 收個人化早報）
- [ ] **Streamlit 網頁加入 Profile 查詢**（管理員後台加一欄）
- [ ] **長浪警戒主動通知**（當浪高>1.5m & 週期>8s 立即推播）
- [ ] **訂閱網頁雲端部署**（Streamlit Cloud）

---

## 快速啟動指令

```bash
cd ~/Downloads/surf_robot

# 安裝套件
pip3 install -r requirements.txt

# 啟動訂閱網頁
streamlit run app.py

# 測試廣播（立即執行）
python3 broadcast.py --now

# 啟動 Webhook（本機測試）
python3 webhook.py

# 啟動廣播排程（每日 06:00）
python3 broadcast.py
```
