# LINE Webhook 串接設定步驟

記錄「浪況機器人」怎麼把 LINE 官方帳號跟這支 Flask 程式接起來。**這份文件只記錄操作步驟，不放任何真實金鑰**——金鑰只存在 `.env` / Render Environment / Streamlit Secrets，三個地方都不會進 git（見 `.gitignore`）。

## 整體流程一覽

```
LINE Developers Console（設定 Webhook URL、拿金鑰）
        ↓
Render.com（部署 webhook.py，提供對外網址）
        ↓
使用者傳訊息給 LINE 官方帳號
        ↓
LINE 伺服器 POST 事件到 Webhook URL
        ↓
webhook.py 的 /webhook 路由接收、驗證、處理
```

前兩步是「一次性設定」，在 LINE 官方網頁後台跟 Render 後台點滑鼠完成，**不會出現在 GitHub 的程式碼裡**；後兩步才是每次使用者互動都會跑的程式邏輯。

---

## 步驟 1：建立 LINE 官方帳號 + Provider

1. 到 [LINE Developers Console](https://developers.line.biz/console/) 用 LINE 帳號登入
2. 建立一個 **Provider**（可以想成「公司/專案分類」，一個 Provider 底下可以放多個 Channel）
3. 在 Provider 底下建立一個 **Messaging API Channel**（這才是真正的「機器人」本體）
   - 填入名稱（本專案是「WaveForecast浪況機器人」）、分類、說明等基本資料
   - 建立完成後會拿到一個 Basic ID（本專案是 `@457fdtbo`），這是使用者加好友時看到的 ID

## 步驟 2：拿 Channel Secret 與 Channel Access Token

進到剛建立的 Channel → 上方分頁：

- **Basic settings** 分頁 → 找到 **Channel secret**，這組對應程式碼裡的 `LINE_CHANNEL_SECRET`（`config.py` 讀這個環境變數），是驗證「這則 webhook 事件真的是 LINE 送來的，不是別人假冒的」用的
- **Messaging API** 分頁 → 拉到 **Channel access token** 區塊，按 Issue（發行）拿到一組 long-lived token，對應程式碼裡的 `LINE_CHANNEL_ACCESS_TOKEN`（`line_api.py` 呼叫 push/reply API 時帶在 `Authorization: Bearer` header）

拿到這兩組值後，填進本機的 `.env`（複製 `.env.example` 改名）跟 Render 的 Environment Variables，**兩邊要填一樣的值**。

⚠️ **踩過的坑**：這兩組金鑰如果不小心 commit 進 git 歷史，就算後來刪除檔案內容，舊 commit 裡還是查得到。本專案曾經在 `PROJECT_PROGRESS.md` 舊版寫死過明文金鑰，發現後有做金鑰輪替（重新 Issue 一次，Console 上舊的會失效）。

## 步驟 3：部署 Flask 服務，拿到對外網址

LINE 只接受 **HTTPS** 的 Webhook URL，本機 `localhost` 或普通 `http://` 都不行。本專案用 Render.com 部署 `webhook.py`（`Procfile` 裡寫 `gunicorn webhook:app`），部署完會拿到一個固定網址，本專案是：

```
https://surf-robot.onrender.com
```

Webhook 的實際端點是這個網址加上 `/webhook`（對應 `webhook.py` 裡 `@app.route("/webhook", methods=["POST"])` 這行）。

## 步驟 4：回到 LINE Console 填 Webhook URL

回到 **Messaging API** 分頁：

1. **Webhook URL** 欄位填入 `https://surf-robot.onrender.com/webhook`
2. 按右邊的 **Verify** 按鈕——LINE 會馬上送一個測試請求到這個網址，如果程式有正常回應（HTTP 200），才會顯示成功。**這一步一定要先部署好、程式沒有崩潰才會過**
3. 打開 **Use webhook** 開關（預設是關的，不開的話 LINE 收到訊息不會轉發給你的程式）
4. 建議關掉 **Auto-reply messages** 跟 **Greeting messages** 這兩個 LINE 內建的自動回覆功能，不然會跟自己寫的機器人邏輯打架（使用者傳訊息時會同時收到 LINE 內建回覆＋自己程式的回覆）

## 步驟 5：程式碼端怎麼接住這個 Webhook

對應 `webhook.py`：

```python
@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data()

    if not verify_signature(body, signature):
        abort(400, "Invalid signature")

    events = request.json.get("events", [])
    threading.Thread(target=_process_events, args=(events,), daemon=True).start()
    return "OK", 200
```

- `verify_signature()`：用 `LINE_CHANNEL_SECRET` 對請求內容算一次 HMAC-SHA256，比對 LINE 傳來的 `X-Line-Signature` header——確保這則請求真的是 LINE 官方送的，不是別人猜到網址亂打的
- **先回 200 再處理事件**：LINE 規定 Webhook 要在幾秒內回應，不然會認定失敗並重送同一事件。本專案把實際處理（查浪況、回訊息）丟進背景執行緒，先讓 LINE 端收到 200，避免因為呼叫外部氣象 API 太慢而被重送、造成訊息重複

## 步驟 6：本機開發怎麼測試（不用每次都部署到 Render）

LINE 一定要 HTTPS 網址，本機開發用 [ngrok](https://ngrok.com/) 開一個暫時的公開通道轉接：

```bash
python3 webhook.py        # 本機啟動 Flask，預設 5000 port
ngrok http 5000            # 另開一個終端機視窗，會給一個暫時的 https://xxxx.ngrok.io 網址
```

把 ngrok 給的網址（記得加 `/webhook`）**暫時**填到 LINE Console 的 Webhook URL 去測試，測完別忘記改回 Render 的正式網址（ngrok 免費版網址每次重開都會變，不能長期用）。

## 加好友連結 / QRCode

Channel 建立好之後，**Messaging API** 分頁最下面會有現成的 QRCode 圖片，加好友連結格式固定是：

```
https://line.me/R/ti/p/%40你的BasicID
```

本專案用在 `tidelog-site/subscribe.html`（衝浪部落格的訂閱頁）跟 footer 的 LINE 圖示連結。

---

## 常見卡關對照表

| 症狀 | 原因 |
|------|------|
| 按 Verify 一直失敗 | Render 服務還沒部署好、或程式碼有 bug 導致回應不是 200；也可能是免費方案服務進入休眠，Verify 請求剛好在冷啟動期間逾時 |
| Console 存 Webhook URL 沒問題，但實際傳訊息機器人沒反應 | 檢查 **Use webhook** 開關有沒有打開；這是最常見的漏設定 |
| 傳訊息機器人回「訊息傳送失敗」 | 通常是 `verify_signature()` 沒過（Channel Secret 填錯或兩邊環境變數不一致），或 Channel Access Token 過期/被輪替過但某一端沒更新 |
| 收到重複回覆 | Webhook 處理太慢被 LINE 重送事件，檢查是否卡在同步等待外部 API |
