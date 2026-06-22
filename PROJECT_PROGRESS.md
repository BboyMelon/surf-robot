# 🌊 浪況機器人專案進度

## 專案資訊
- **專案名稱**：LINE 浪況自動訂閱與回報機器人
- **專案路徑**：`/Users/melon/Downloads/surf_robot/`
- **最後更新**：2026-05-25
- **部署網址**：https://surf-robot.onrender.com
- **GitHub**：https://github.com/BboyMelon/surf-robot

---

## 技術架構

| 元件 | 技術 | 說明 |
|------|------|------|
| 前端後台 | Python Streamlit | 訂閱名單 + Surfer 檔案 + 推播管理 |
| 後端 Webhook | Python Flask | LINE 事件接收 + 背景排程執行緒 |
| 廣播排程 | Python schedule + threading | 05:00 廣播 / 每 3h 長浪警戒 / 每 1h 颱風 |
| 雲端資料庫 | Supabase (PostgreSQL) | members / groups / profiles |
| 主要浪況資料 | CWA O-B0075-001 | 氣象署浮標站即時海象 |
| 備援浪況資料 | Open-Meteo Marine API | Render 海外 IP 自動切換，免費無 Token |
| 颱風資料 | CWA W-C0034-005 | 颱風警報偵測 |
| 推播 | LINE Messaging API | Push Message + Reply Message |
| 部署 | Render.com（Free）| gunicorn 單 worker |
| 持續運作 | GitHub Actions | 每 5 分鐘 ping /health 防 spin-down |

---

## 金鑰與設定（存於 .env）

| 變數 | 說明 |
|------|------|
| `CWA_API_KEY` | `CWA-548E18F6-09C1-4F44-A924-9E18773BFF4D` |
| `LINE_CHANNEL_ACCESS_TOKEN` | 已設定 |
| `LINE_CHANNEL_SECRET` | `13acce66c3d54a067e2c46afd1d6bf7d` |
| `SUPABASE_URL` | `https://byrzvtpctudqhqfzeyom.supabase.co` |
| `SUPABASE_KEY` | 已設定 |

---

## 檔案結構

```
surf_robot/
├── .env                    ✅ 所有金鑰（勿上傳 git）
├── .env.example            ✅ 金鑰範本
├── .gitignore              ✅
├── Procfile                ✅ gunicorn webhook:app
├── config.py               ✅ 浪點設定、陸風方向、GoOcean 分級
├── db.py                   ✅ Supabase/SQLite 資料庫層（含 update_display_name）
├── app.py                  ✅ Streamlit 後台（訂閱名單 + Surfer 檔案 + 推播管理）
├── webhook.py              ✅ LINE Webhook + 背景排程執行緒
├── broadcast.py            ✅ 廣播 + 警戒 + 個人化推播 + Open-Meteo fallback
├── setup_richmenu.py       ✅ LINE 圖文選單建立腳本（一次性本機工具）
├── richmenu.png            ✅ 選單圖片（已上傳 LINE）
├── requirements.txt        ✅
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
id, line_id (UNIQUE), display_name, gender, surf_years, board_type, fav_spots, updated_at
```
> `display_name` 欄位 2026-05-22 新增，每次互動自動更新

---

## 監測浪點（共 15 個）

### 🔵 北部（5 個）
| 浪點 | 浮標站 |
|------|--------|
| 金山沙珠灣 | `46778A` |
| 翡翠灣 | `C6AH2` |
| 中角灣 | `46778A` |
| 烏石港 | `46757B` |
| 宜蘭外澳 | `46757B` |

### 🟡 中部（2 個）
| 浪點 | 浮標站 |
|------|--------|
| 松柏港福德里 | `46714D` |
| 外埔漁港 | `COMC08` |

### 🟠 東部（4 個）
| 浪點 | 浮標站 |
|------|--------|
| 花蓮北濱公園 | `46706A` |
| 花蓮環保公園 | `46706A` |
| 台東金樽 | `46761F` |
| 台東東河 | `46761F` |

### 🔴 南部（4 個）
| 浪點 | 浮標站 |
|------|--------|
| 台南漁光島 | `46699A` |
| 恆春南灣 | `46694A` |
| 恆春九鵬 | `C6S94` |
| 恆春佳樂水 | `46694A` |

---

## 排程（Render 背景執行緒）

| 時間 | 任務 |
|------|------|
| 每日 05:00 | `broadcast()` 全台浪況廣播 |
| 每 3 小時 | `check_swell_alerts()` 長浪警戒偵測 |
| 每 1 小時 | `check_typhoon_alerts()` 颱風警報偵測 |

---

## LINE 圖文選單（2×2 格）

| 格 | 名稱 | 觸發文字 | 回應 |
|----|------|---------|------|
| 1 | 🔍 即時浪況查詢 | 點擊後提示輸入浪點 | 引導文字 |
| 2 | 📝 Surfer 檔案建立 | 彈出填表格式 | 表單文字 |
| 3 | 📚 專業海象觀測網 | Flex Message | CWA / NODASS / Swell Eye 連結 |
| 4 | 🗺️ Windy 動態地圖 | 回傳 Windy 台灣浪況網址 | ✅ 已修正 |

---

## LINE 指令

| 使用者傳送 | 機器人回應 |
|-----------|-----------|
| 浪點名稱（如：烏石港、中角、金樽）| 即時浪況卡片 |
| 地區名稱（如：北部、東部、南部）| 該地區所有浪點 |
| 性別/浪齡/版型/常衝浪點 格式 | 建立/更新 Profile |
| 我的資料 | 查詢目前 Surfer 檔案 |
| 我的ID | 回覆 LINE 顯示名稱 |

---

## 訊息格式（卡片風）

```
┌ 📍 烏石港
│ 🌊 1.2m · 8s · E  💨W 5.3m/s
│ 🟡 浪人推薦：中階  ✅陸風  ⚡9.6
│ 👤 🤙 不錯的浪！適合你的程度，衝吧！
└ ⚠️ 防波堤北側礁岩區，注意退流
```

---

## 已完成功能 ✅（截至 2026-05-22）

- [x] Streamlit 後台（訂閱名單 / Surfer 檔案 / 推播管理按鈕）
- [x] Supabase 三張表 + RLS + `display_name` 欄位
- [x] CWA O-B0075-001 浮標 API（15 浪點）
- [x] Open-Meteo Marine 備援（Render 海外 IP 自動切換）✅
- [x] Swell Eye 湧浪能量、浪人推薦等級、陸風判斷
- [x] 每日 05:00 廣播（通用版 + 個人化版）
- [x] 長浪警戒自動推播（波高 ≥ 1.5m 且週期 ≥ 8s，6h de-dup）✅
- [x] 颱風警報自動推播（CWA W-C0034-005，新 ID 才推）✅
- [x] 背景排程執行緒（Render 上廣播正式生效）✅
- [x] Render.com 部署 + GitHub Actions keep-alive ✅
- [x] 即時浪況查詢（卡片格式）✅
- [x] LINE 顯示名稱自動記錄進 profiles ✅
- [x] 未填資料用戶提醒推播（後台按鈕觸發）✅
- [x] Windy 動態地圖按鈕修正（直接連結）✅
- [x] 訊息格式優化（卡片風 ┌│└）✅
- [x] 地區重整：北部5點、東部合併、中部改名 ✅
- [x] 廣播測試成功（真實推播到 LINE）✅

---

## 待辦清單

### 🟡 下一步
- [ ] **今日最佳浪點推薦**：廣播加入能量最高 + 陸風條件的推薦浪點
- [x] **明日預報**：Open-Meteo hourly，廣播底部附概覽 + 「明日」指令查完整版 ✅

### 🟢 低優先
- [ ] 訂閱開關（用戶自助暫停/恢復）
- [x] 潮汐時間 ✅（CWA F-A0021-001，2026-06-22 完成。`config.py` 新增 `TIDE_STATION_MAP` 15浪點對應潮汐站；`broadcast.py` 新增 `fetch_tide_today()` / `build_tide_line()`；單一浪點即時查詢會附上今日滿潮/乾潮時刻表 + 下次潮汐倒數）
- [x] Render 設定自動部署 ✅（GitHub Actions push main 自動觸發 Deploy Hook，已於 2026-06-12 確認運作中）
- [x] Streamlit 後台部署 ✅（2026-06-12 部署到 Streamlit Community Cloud，手機可直接開網址查看 Surfer 檔案/訂閱名單，App 分享設定為 Public，管理員密碼 `surf123`）

### 💡 未來功能（暫緩）
- [ ] **影片連結投稿**：浪友傳 `📹 烏石港 https://...`，機器人存 surf_videos 表，廣播附「今日影片」

---

## LINE 推播額度說明

| 方案 | Push 額度 | Reply |
|------|----------|-------|
| 免費 | 500 則/月 | 無限制 |

**目前用量估算**（1 位訂閱者）：
- 每日廣播 × 30 天 = 30 則/月
- 警戒推播（偶發）≈ 5 則/月
- **合計約 35 則/月**，離上限還很遠

> ⚠️ 超過 16 位訂閱者時每日廣播才會逼近 500 則/月上限

---

## 快速啟動指令

```bash
cd ~/Downloads/surf_robot

# 廣播測試（立即執行）
python3 broadcast.py --now

# 本機 Webhook（需搭配 ngrok）
python3 webhook.py

# ngrok 隧道（另開視窗）
ngrok http 5000

# 後台管理網頁
streamlit run app.py

# 重建圖文選單（一次性）
python3 setup_richmenu.py
```
