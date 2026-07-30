"""
LINE Webhook 監聽伺服器 — Flask
處理：JoinEvent / FollowEvent / 使用者 Profile 填寫解析
"""
import re
import hashlib
import hmac
import base64
import threading
import time
import schedule
from datetime import datetime
from flask import Flask, request, abort, jsonify
from config import LINE_CHANNEL_SECRET, SURF_SPOTS_CONFIG, BROADCAST_TOKEN, TIDE_STATION_MAP, STREAMLIT_URL, TIDELOG_ALLOWED_ORIGINS
from db import add_member, add_group, remove_member, remove_group, save_profile, get_profile, update_display_name, pause_member, resume_member, get_member_status, has_alert_logged
from line_api import (
    push_text as push_message,
    push_flex,
    reply_text as reply_message,
    reply_flex,
    get_display_name as get_line_display_name,
    verify_line_user,
)
from broadcast import (
    get_marine_data,
    SPOT_STATION_MAP, build_spot_block,
    broadcast, check_swell_alerts, check_typhoon_alerts,
    fetch_tomorrow_forecast, build_tomorrow_full_report,
    build_overview_report, get_all_spots_status,
    fetch_tide_today, build_tide_line,
    TW_TZ,
)

app = Flask(__name__)

# ── 常衝浪點選單（動態從 config 產生）────────────────────────
def build_spot_menu() -> str:
    categories = {}
    for spot, cfg in SURF_SPOTS_CONFIG.items():
        cat = cfg.get("category", "其他")
        categories.setdefault(cat, []).append(spot)
    lines = ["📍 常衝浪點範例（可填多個，逗號分隔）："]
    for cat, spots in categories.items():
        lines.append(f"{cat}：{'、'.join(spots)}")
    return "\n".join(lines)

# ── 地區關鍵字 → 浪點對應 ─────────────────────────────────────
REGION_SPOTS = {
    "北部": ["金山中角灣（沙珠灣）", "翡翠灣", "烏石港", "宜蘭外澳", "福隆"],
    "中部": ["松柏港福德里", "外埔漁港"],
    "東部": ["花蓮北濱公園", "花蓮環保公園", "台東金樽", "台東東河"],
    "花蓮": ["花蓮北濱公園", "花蓮環保公園"],
    "台東": ["台東金樽", "台東東河"],
    "南部": ["台南漁光島", "恆春南灣", "恆春九鵬", "恆春佳樂水"],
    "恆春": ["恆春南灣", "恆春九鵬", "恆春佳樂水"],
    "墾丁": ["恆春南灣", "恆春佳樂水"],
}

def detect_query_spots(text: str) -> list:
    """從訊息文字偵測要查詢的浪點，回傳浪點名稱清單。"""
    matched = []
    # 地區關鍵字
    for region, spots in REGION_SPOTS.items():
        if region in text:
            for s in spots:
                if s not in matched:
                    matched.append(s)
    # 浪點名稱（部分比對）
    for spot in SPOT_STATION_MAP:
        if spot in text or any(part in text for part in spot.split("/")):
            if spot not in matched:
                matched.append(spot)
    # 短名稱比對（例：烏石港、外澳、南灣、金山、外埔）
    SHORT_MAP = {
        "外澳": "宜蘭外澳", "烏石": "烏石港",
        "北濱": "花蓮北濱公園", "環保公園": "花蓮環保公園",
        "金樽": "台東金樽", "東河": "台東東河",
        "漁光": "台南漁光島", "南灣": "恆春南灣",
        "九鵬": "恆春九鵬", "佳樂水": "恆春佳樂水",
        "金山": "金山中角灣（沙珠灣）", "沙珠灣": "金山中角灣（沙珠灣）",
        "中角": "金山中角灣（沙珠灣）", "翡翠灣": "翡翠灣",
        "松柏港": "松柏港福德里", "福德里": "松柏港福德里",
        "外埔": "外埔漁港",
    }
    for short, full in SHORT_MAP.items():
        if short in text and full not in matched:
            matched.append(full)
    return matched


def build_instant_report(spots: list, marine: dict, profile: dict = None) -> str:
    """即時查詢回報：只顯示指定浪點資料。"""
    from datetime import datetime
    now = datetime.now().strftime("%m/%d %H:%M")
    lines = [f"🌊 即時浪況查詢｜{now}\n"]

    for spot_name in spots:
        cfg        = SURF_SPOTS_CONFIG.get(spot_name, {})
        station_id = SPOT_STATION_MAP.get(spot_name)
        data       = marine.get(station_id, {}) if station_id else {}

        tide_id   = TIDE_STATION_MAP.get(spot_name)
        tide_line = build_tide_line(fetch_tide_today(tide_id)) if tide_id else ""

        lines.extend(build_spot_block(spot_name, cfg, data, profile=profile, tide_line=tide_line))
        lines.append("")

    source = marine.get("_meta", {}).get("source", "cwa")
    lines.append("📡 " + ("Open-Meteo Marine（模型預報）" if source == "open-meteo" else "中央氣象署 O-B0075-001"))
    return "\n".join(lines)

# ── 加好友歡迎訊息 ────────────────────────────────────────────
def build_welcome(is_group: bool = False) -> str:
    return """🏄‍♂️ 歡迎加入【黃金浪況預報小助手】！
我們會為您精準守候台灣各大浪點，讓您不再錯過起浪好日子！

⏰ 【每日定時報浪時間】
完成下方訂閱表單即可解鎖每日 05:00 自動推播，結合 Swell Eye 湧浪能量與 GoOcean 安全評級的精準浪況簡報！

📋 輸入「訂閱」前往官方訂閱表單，解鎖每日推播＋完整功能＋瀏覽衝浪相關電子報資訊！

👇 【自助功能選單】
手機下方已為您準備快捷圖文選單，動動手指即可解鎖更多衝浪黑科技！

🔍 即時浪況查詢 — 輸入區域或浪點名稱立即查
📝 Surfer 檔案建立 — 建立個人資料，解鎖客製化建議
📚 專業海象觀測網 — 精選三大海象資料來源
🗺️ Windy 動態地圖 — 一鍵查看台灣浪高粒子圖

💬 有任何建議或想新增的浪點，歡迎隨時留言！
祝您天天 Shred Hard、安全下海！🌊"""

# ── 解析使用者回傳的 Profile 訊息 ────────────────────────────
def parse_profile(text: str) -> dict:
    """
    偵測並解析格式：
      名稱：阿翔
      性別：男
      浪齡：3
      衝浪板型：短板
      常衝浪點：烏石港、外澳
    回傳 dict，無法解析則回傳空 {}
    """
    if "性別" not in text or "浪齡" not in text:
        return {}

    def extract(pattern, t):
        m = re.search(pattern, t)
        return m.group(1).strip() if m else ""

    nickname   = extract(r"名稱[：:]\s*(.+)", text)
    gender     = extract(r"性別[：:]\s*(.+)", text)
    years_raw  = extract(r"浪齡[：:]\s*(\d+)", text)
    board_type = extract(r"(?:版型|衝浪板型)[：:]\s*(.+)", text)
    fav_spots  = extract(r"常衝浪點[：:]\s*(.+)", text)

    surf_years = int(years_raw) if years_raw.isdigit() else 0

    profile = {
        "gender":     gender,
        "surf_years": surf_years,
        "board_type": board_type,
        "fav_spots":  fav_spots,
    }
    if nickname:
        profile["nickname"] = nickname
    return profile

# ── 根據 profile 判斷技術等級 ──────────────────────────────────
def skill_label(surf_years: int) -> str:
    if surf_years <= 1:
        return "🌱 新手衝浪者"
    elif surf_years <= 4:
        return "🏄 中級衝浪者"
    else:
        return "🔥 進階衝浪者"

# ── 指令總覽 ──────────────────────────────────────────────────
HELP_TEXT = """📖 指令總覽

📋 【訂閱】
  訂閱 → 前往官方訂閱表單，解鎖每日推播

🗺️ 【全台總覽】
  總覽 → 每區一行精簡摘要

🌊 【即時浪況查詢】
直接輸入區域或浪點名稱：
  北部 / 中部 / 東部 / 南部
  花蓮 / 台東 / 恆春 / 墾丁
  烏石港、外澳、翡翠灣、南灣…
  （單一浪點查詢會附上今日潮汐時刻 🌙）

📅 【預報查詢】
  明日 / 明天浪況 / 明日預報

🏆 【每日廣播】
  每日 05:00 自動推播，含：
  · 今日最佳浪點推薦 🥇🥈🥉
  · 15 大浪點完整報告
  · 明日浪況概況

👤 【個人資料】
  我的資料 → 查看 Surfer 檔案
  我的ID   → 查看 LINE ID
  已建檔後若要修改，請在表單開頭加上「修改」二字

🔕 【推播開關】
  暫停推播 → 暫停每日廣播（隨時可恢復）
  恢復推播 → 重新開啟每日廣播

⏰ 【自動警戒】
  長浪警戒（波高 ≥1.5m 且週期 ≥8s）
  颱風通知（距台灣 1000km 內）

💡 輸入浪點名稱即可即時查詢！"""

# ── 圖文選單：即時浪況查詢 ───────────────────────────────────
SPOT_QUERY_HINT = """🔍 即時浪況查詢

請輸入區域關鍵字或浪點名稱，小助手立刻為您抓取最新海象！

📍 區域關鍵字：
  北部、宜蘭、中部、東部、南部

📍 浪點名稱範例：
  烏石港、外澳、沙珠灣、翡翠灣
  金山、外埔、北濱、金樽、南灣

直接回傳關鍵字即可 👇"""

# ── 圖文選單：Surfer 檔案建立 ──────────────────────────────
PROFILE_FORM = """📝 填寫小資料，解鎖客製化浪況建議！

請複製以下格式，填寫後直接回傳 👇

━━━━━━━━━━━━
名稱：（你想被稱呼的名字）
性別：（男 / 女 / 其他）
浪齡：（例：3）
版型：（長板 / 短板 / 中長板）
常衝浪點：（填入你常去的浪點）
━━━━━━━━━━━━

建立後每日 05:00 推送專屬浪況早報 🌊
💡 已建立過檔案的話，請在開頭加上「修改」二字再重新填寫，才能更新資料喔！"""

# ── 圖文選單：浪況數據與直播資源 Flex Carousel ─────────────
def _uri_btn(label: str, uri: str, color: str, height: str = "md") -> dict:
    return {
        "type": "button", "style": "primary", "color": color, "height": height,
        "action": {"type": "uri", "label": label, "uri": uri},
    }


def build_resources_flex() -> dict:
    def _hdr(text: str, bg: str) -> dict:
        return {
            "type": "box", "layout": "vertical",
            "backgroundColor": bg, "paddingAll": "12px",
            "contents": [{"type": "text", "text": text,
                          "color": "#ffffff", "weight": "bold", "size": "lg"}],
        }

    def _body(btns: list) -> dict:
        return {"type": "box", "layout": "vertical", "spacing": "sm", "contents": btns}

    b1 = {
        "type": "bubble",
        "header": _hdr("📊 海象觀測資源", "#0D4F8C"),
        "body": _body([
            _uri_btn("🌊 中央氣象署 CWA 海象資訊", "https://www.cwa.gov.tw/V8/C/M/OBS_Marine.html", "#1a5fa8"),
            _uri_btn("🔬 國家海洋研究院 NODASS", "https://nodass.namr.gov.tw/", "#0A6B5E"),
            _uri_btn("🏄 Surf-Forecast.com", "https://www.surf-forecast.com/", "#C45D00"),
            _uri_btn("🗺️ Windy 動態地圖", "https://www.windy.com/?waves,23.8,121.8,6", "#3D1A70"),
        ]),
    }

    b2 = {
        "type": "bubble",
        "header": _hdr("🔴 北部浪況直播", "#9B1515"),
        "body": _body([
            _uri_btn("▶ 中角灣", "https://www.youtube.com/watch?v=iJphhU-iaTA", "#CC0000", "sm"),
            _uri_btn("▶ 中角灣（國海院）", "https://www.youtube.com/watch?v=Jpg_V7f7rW8", "#CC0000", "sm"),
            _uri_btn("▶ 白沙灣", "https://www.youtube.com/watch?v=FbB8WDUXXqU", "#CC0000", "sm"),
            _uri_btn("▶ 外澳沙灘", "https://www.youtube.com/watch?v=UgoT-QTbYvo", "#CC0000", "sm"),
            _uri_btn("▶ 福隆海水浴場", "https://www.youtube.com/watch?v=Rhkr8qJOFO4", "#CC0000", "sm"),
            _uri_btn("▶ 福隆（國海院）", "https://www.youtube.com/watch?v=Yhj5qvupJDk", "#CC0000", "sm"),
            _uri_btn("▶ 無尾港", "https://www.youtube.com/watch?v=7S0lZRj9ViY", "#CC0000", "sm"),
        ]),
    }

    b3 = {
        "type": "bubble",
        "header": _hdr("🔴 東部浪況直播", "#0A5E50"),
        "body": _body([
            _uri_btn("▶ 金樽", "https://www.youtube.com/watch?v=q3KJt-SZc2s", "#0A7A6E", "sm"),
            _uri_btn("▶ 金樽休憩中心", "https://www.youtube.com/watch?v=ZdqHgQwvZOw", "#0A7A6E", "sm"),
            _uri_btn("▶ 都歷遊客中心", "https://www.youtube.com/watch?v=JhQuR77AR7U", "#0A7A6E", "sm"),
            _uri_btn("▶ 杉原灣海灘", "https://www.youtube.com/watch?v=VqS_Y8ZCj6M", "#0A7A6E", "sm"),
        ]),
    }

    b4 = {
        "type": "bubble",
        "header": _hdr("🔴 南部浪況直播", "#B84D00"),
        "body": _body([
            _uri_btn("▶ 旗津海灘", "https://www.youtube.com/watch?v=ka7FV0sCvxQ", "#CC5500", "sm"),
            _uri_btn("▶ 旗津海灘（國海院）", "https://www.youtube.com/watch?v=An0oUZBZtG0", "#CC5500", "sm"),
            _uri_btn("▶ 南灣", "https://www.youtube.com/watch?v=jUnFuJSj0OU", "#CC5500", "sm"),
            _uri_btn("▶ 佳樂水", "https://www.youtube.com/watch?v=35ov7d8zLyE", "#CC5500", "sm"),
            _uri_btn("▶ 佳樂水（國海院）", "https://www.youtube.com/watch?v=8bn_-PbneiI", "#CC5500", "sm"),
        ]),
    }

    return {
        "type": "flex",
        "altText": "📺 浪況數據與直播資源",
        "contents": {"type": "carousel", "contents": [b1, b2, b3, b4]},
    }

# ── 圖文選單：訂閱表單邀請 Flex Message ─────────────────────
def build_subscribe_flex() -> dict:
    return {
        "type": "flex",
        "altText": "📋 立即訂閱浪況推播",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#0A6B5E",
                "contents": [{
                    "type": "text",
                    "text": "📋 立即訂閱浪況推播",
                    "color": "#ffffff",
                    "weight": "bold",
                    "size": "lg",
                }],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": "完成訂閱後，才能啟用每日 05:00 自動推播浪況功能，並可在訂閱頁瀏覽衝浪相關電子報與資訊 🌊",
                        "wrap": True,
                        "size": "sm",
                        "color": "#444444",
                    },
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#0A6B5E",
                        "action": {
                            "type": "uri",
                            "label": "🌊 前往訂閱表單",
                            "uri": STREAMLIT_URL,
                        },
                    },
                ],
            },
        },
    }

# ── 未建檔提示 ────────────────────────────────────────────────
def build_no_profile_prompt(name: str = "") -> str:
    greeting = f"嗨，{name}！" if name else "嗨！"
    spot_menu = build_spot_menu()
    return f"""{greeting}

尚未建立衝浪檔案 🏄

建立後每天早上 05:00 會依你的程度與常衝浪點，推送專屬浪況建議！

請複製以下格式填寫後回傳 👇

━━━━━━━━━━━━
名稱：（你想被稱呼的名字）
性別：（男 / 女 / 其他）
浪齡：（例：3）
版型：（長板 / 短板 / 中長板）
常衝浪點：（填入你常去的浪點）
━━━━━━━━━━━━

{spot_menu}"""

# ── 回覆確認訊息 ──────────────────────────────────────────────
def build_profile_confirm(profile: dict, is_update: bool = False) -> str:
    label = skill_label(profile.get("surf_years", 0))
    title = "✅ 衝浪檔案已更新！" if is_update else "✅ 衝浪檔案建立完成！"
    nickname = profile.get("nickname") or profile.get("display_name") or "未填"
    return f"""{title}

📛 名稱：{nickname}
👤 性別：{profile.get('gender', '未填')}
🏄 浪齡：{profile.get('surf_years', 0)} 年
🛹 板型：{profile.get('board_type', '未填')}
📍 常衝浪點：{profile.get('fav_spots', '未填')}
⭐ 等級判定：{label}

從明天起每日 05:00 我會依照你的程度
推送專屬客製化浪況早報給你！🌊

之後若要修改資料，請在開頭加上「修改」二字後重新填寫表單 🤙"""

# ── LINE 簽章驗證 ─────────────────────────────────────────────
def verify_signature(body: bytes, signature: str) -> bool:
    secret = LINE_CHANNEL_SECRET.encode("utf-8")
    hash_val = hmac.new(secret, body, hashlib.sha256).digest()
    expected = base64.b64encode(hash_val).decode("utf-8")
    return hmac.compare_digest(expected, signature)

# ── Health Check ─────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return "OK", 200


# ── 外部廣播觸發端點（GitHub Actions 05:00 呼叫）────────────
@app.route("/broadcast-now", methods=["POST"])
def trigger_broadcast():
    """由 GitHub Actions 在台灣時間 05:00 呼叫，確保廣播不漏發。"""
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {BROADCAST_TOKEN}":
        abort(403)
    threading.Thread(target=broadcast, daemon=True).start()
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔔 外部廣播觸發成功")
    return "Broadcast triggered", 200


# ── 廣播狀態查詢（供 broadcast_retry.yml 判斷今日是否已成功）──
@app.route("/broadcast-status", methods=["GET"])
def broadcast_status():
    """檢查台灣今日日期是否已有成功廣播紀錄（broadcast() 內 log_alert 寫入）。"""
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {BROADCAST_TOKEN}":
        abort(403)
    today_key = datetime.now(TW_TZ).strftime("%Y-%m-%d")
    success = has_alert_logged("broadcast_success", today_key)
    return {"date": today_key, "success": success}, 200


# ── tidelog-site 訂閱表單端點（Email選填＋LINE ID必填）───────
# 瀏覽器預設擋跨網域請求，手動加 Access-Control-Allow-* 標頭放行
# tidelog-site 網域（不裝 flask-cors 套件，原理更透明）。
def _add_cors_headers(resp):
    origin = request.headers.get("Origin", "")
    if origin in TIDELOG_ALLOWED_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


@app.route("/subscribe", methods=["POST", "OPTIONS"])
def subscribe():
    if request.method == "OPTIONS":
        # 瀏覽器送 JSON POST 前會先送一次 OPTIONS 預檢請求，直接回空200+CORS標頭即可
        return _add_cors_headers(jsonify({})), 200

    data    = request.get_json(silent=True) or {}
    email   = (data.get("email") or "").strip()
    line_id = (data.get("line_id") or "").strip()

    if not line_id.startswith("U"):
        resp = jsonify({"ok": False, "message": "LINE User ID 格式不正確，請確認是否以U開頭"})
        return _add_cors_headers(resp), 400

    valid, display_name = verify_line_user(line_id)
    if not valid:
        resp = jsonify({"ok": False, "message": "找不到這個 LINE ID，請先加機器人好友，並確認 ID 複製正確"})
        return _add_cors_headers(resp), 400

    ok, msg = add_member(email, line_id, form_completed=True)
    resp = jsonify({
        "ok": ok,
        "message": f"訂閱成功，{display_name}！明天早上 05:00 見 🌊" if ok else msg,
    })
    return _add_cors_headers(resp), (200 if ok else 500)


@app.route("/api/live-conditions", methods=["GET"])
def api_live_conditions():
    """公開唯讀端點：供 tidelog-site 互動地圖抓取全浪點目前浪況，不需認證。"""
    marine = get_marine_data()
    spots  = get_all_spots_status(marine) if marine else []
    resp = jsonify({
        "updated_at": datetime.now(TW_TZ).isoformat(),
        "spots": spots,
    })
    return _add_cors_headers(resp)


# ── Webhook 主路由 ────────────────────────────────────────────
# events 的實際處理放進背景執行緒：浪點查詢/總覽/明日預報都會同步打
# CWA/Open-Meteo，慢的話可能要等多秒，LINE 那邊收不到即時的200回應就可能
# 重送同一個事件，導致重複處理（重複回覆、甚至重複建檔）。先回 200 給LINE，
# 實際查資料+回覆訊息在背景做，兩邊互不影響（reply token 不受HTTP回應時機限制）。
@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data()

    if not verify_signature(body, signature):
        abort(400, "Invalid signature")

    events = request.json.get("events", [])
    threading.Thread(target=_process_events, args=(events,), daemon=True).start()
    return "OK", 200


def _process_events(events: list) -> None:
    for event in events:
        try:
            event_type  = event.get("type")
            source      = event.get("source", {})
            source_type = source.get("type")
            reply_token = event.get("replyToken", "")

            # ── 個人加好友 ────────────────────────────────────────
            if event_type == "follow" and source_type == "user":
                user_id = source.get("userId")
                add_member(email="", line_id=user_id)
                push_message(user_id, build_welcome(is_group=False))
                print(f"[Follow] {user_id}")

            # ── 封鎖 / 取消加好友 ─────────────────────────────────
            elif event_type == "unfollow" and source_type == "user":
                user_id = source.get("userId")
                remove_member(user_id)
                print(f"[Unfollow] {user_id}")

            # ── 機器人加入群組 ────────────────────────────────────
            elif event_type == "join" and source_type == "group":
                group_id = source.get("groupId")
                add_group(group_id)
                push_message(group_id, build_welcome(is_group=True))
                print(f"[Join] {group_id}")

            # ── 機器人被踢出群組 ──────────────────────────────────
            elif event_type == "leave" and source_type == "group":
                group_id = source.get("groupId")
                remove_group(group_id)
                print(f"[Leave] {group_id}")

            # ── 文字訊息處理 ──────────────────────────────────────
            elif event_type == "message" and event.get("message", {}).get("type") == "text":
                msg_text = event["message"]["text"]
                user_id  = source.get("userId", "")

                # 只在 DB 尚無名稱時才呼叫 LINE API（減少呼叫次數）
                if user_id:
                    existing = get_profile(user_id)
                    if not existing or not existing.get("display_name"):
                        display_name = get_line_display_name(user_id)
                        update_display_name(user_id, display_name)

                # ── 圖文選單觸發（reply 失敗時用 push 備援，防止部署重啟空窗期 token 過期）──
                # 文字比對同時接受圖文選單送出的完整emoji版本，跟使用者手動輸入的純文字版本
                if "即時浪況查詢" in msg_text:
                    if not reply_message(reply_token, SPOT_QUERY_HINT) and user_id:
                        push_message(user_id, SPOT_QUERY_HINT)

                elif "Surfer 檔案建立" in msg_text:
                    if not reply_message(reply_token, PROFILE_FORM) and user_id:
                        push_message(user_id, PROFILE_FORM)

                elif "浪況數據與直播資源" in msg_text or "專業海象觀測網" in msg_text:
                    flex = build_resources_flex()
                    if not reply_flex(reply_token, flex) and user_id:
                        push_flex(user_id, flex)

                elif "Windy 動態地圖" in msg_text:
                    windy_msg = "🗺️ Windy 動態地圖\n\n點擊下方連結，查看台灣即時浪高與湧浪粒子動圖 👇\nhttps://www.windy.com/?waves,23.8,121.8,6"
                    if not reply_message(reply_token, windy_msg) and user_id:
                        push_message(user_id, windy_msg)

                # 訂閱表單邀請
                elif any(k in msg_text for k in ["訂閱", "立即訂閱", "加入訂閱", "訂閱表單"]):
                    flex = build_subscribe_flex()
                    if not reply_flex(reply_token, flex) and user_id:
                        push_flex(user_id, flex)

                # 查詢自己名稱
                elif any(k in msg_text for k in ["我的ID", "我的id", "my id", "ID是", "我的名稱"]):
                    name = get_line_display_name(user_id)
                    reply_message(reply_token, f"你好，{name}！\n你的 LINE 名稱是：{name}")

                # 填寫/更新 Profile（同一 LINE ID 只會有一筆檔案；已建檔過的話，
                # 必須在訊息加上「修改/更新」才會覆寫，避免誤觸或重複建檔）
                elif "性別" in msg_text and "浪齡" in msg_text:
                    existing_profile = get_profile(user_id)
                    wants_edit = any(k in msg_text for k in ["修改", "更新", "edit"])

                    if existing_profile and not wants_edit:
                        reply_message(reply_token,
                            "你已經建立過 Surfer 檔案了 🏄\n"
                            "若要修改資料，請在開頭加上「修改」二字，再依照格式重新填寫並回傳喔！\n\n"
                            "輸入「我的資料」可先查看目前的檔案內容。")
                    else:
                        profile = parse_profile(msg_text)
                        if profile and user_id:
                            ok, msg = save_profile(user_id, profile)
                            if ok:
                                # 建檔成功＝自動開通05:00廣播（form_completed=True），
                                # 不用再另外跑一次網站表單。add_member是upsert，重複呼叫不會出錯。
                                member_ok, member_msg = add_member("", user_id, form_completed=True)
                                if not member_ok:
                                    print(f"[自動開通推播失敗] {user_id} → {member_msg}")
                                merged = {**(existing_profile or {}), **profile}
                                reply_message(reply_token, build_profile_confirm(merged, is_update=bool(existing_profile)))
                                print(f"[Profile {'更新' if existing_profile else '儲存'}] {user_id} → {profile}")
                            else:
                                reply_message(reply_token, "⚠️ 資料儲存失敗，請稍後再試一次。")
                                print(f"[Profile 儲存失敗] {user_id} → {msg}")
                        else:
                            reply_message(reply_token, "格式好像有點問題 🤔\n請參考範例重新填寫喔！")

                # 查詢自己的 Profile
                elif any(k in msg_text for k in ["我的資料", "我的檔案", "查詢資料"]):
                    p = get_profile(user_id)
                    if p:
                        reply_message(reply_token, build_profile_confirm(p))
                    else:
                        reply_message(reply_token, build_no_profile_prompt())

                # 暫停推播
                elif any(k in msg_text for k in ["暫停推播", "暫停訂閱", "停止推播", "停止訂閱"]):
                    status = get_member_status(user_id)
                    if status == "paused":
                        reply_message(reply_token, "你的每日推播已經是暫停狀態了 🔕\n輸入「恢復推播」即可重新開啟。")
                    elif status == "active":
                        ok, _ = pause_member(user_id)
                        if ok:
                            reply_message(reply_token,
                                "🔕 每日浪況推播已暫停。\n\n"
                                "長浪警戒與颱風通知仍會正常推送。\n"
                                "隨時輸入「恢復推播」就可以重新開啟 🌊")
                        else:
                            reply_message(reply_token, "⚠️ 暫停失敗，請稍後再試。")
                    else:
                        reply_message(reply_token,
                            "你目前不在訂閱名單中 🤔\n"
                            "重新加好友即可自動加入每日推播！")

                # 恢復推播
                elif any(k in msg_text for k in ["恢復推播", "繼續推播", "恢復訂閱", "繼續訂閱", "開啟推播"]):
                    status = get_member_status(user_id)
                    if status == "active":
                        reply_message(reply_token, "你的每日推播已經是開啟狀態了 🌊\n每天 05:00 和 15:00 都會收到浪況喔！")
                    elif status == "paused":
                        ok, _ = resume_member(user_id)
                        if ok:
                            reply_message(reply_token,
                                "✅ 每日浪況推播已恢復！\n\n"
                                "每天 05:00（早報）和 15:00（下午快報）都會收到最新浪況 🌊\n"
                                "需要暫停時輸入「暫停推播」即可。")
                        else:
                            reply_message(reply_token, "⚠️ 恢復失敗，請稍後再試。")
                    else:
                        reply_message(reply_token,
                            "你目前不在訂閱名單中 🤔\n"
                            "重新加好友即可自動加入每日推播！")

                # 指令總覽
                elif any(k in msg_text for k in ["help", "Help", "HELP", "指令", "說明", "功能"]):
                    reply_message(reply_token, HELP_TEXT)

                # 全台總覽
                elif any(k in msg_text for k in ["總覽", "全台", "overview"]):
                    marine = get_marine_data()
                    if marine:
                        reply_message(reply_token, build_overview_report(marine))
                    else:
                        reply_message(reply_token, "⚠️ 目前無法取得浪況資料，請稍後再試。")

                # 明日預報查詢
                elif any(k in msg_text for k in ["明日預報", "明天浪況", "明日浪況", "明天預報", "明日"]):
                    forecast = fetch_tomorrow_forecast()
                    if forecast:
                        reply_message(reply_token, build_tomorrow_full_report(forecast))
                    else:
                        reply_message(reply_token, "⚠️ 目前無法取得明日預報資料，請稍後再試。")

                # 其餘訊息：先嘗試浪點查詢，否則引導未建檔用戶填資料
                # （跟上面圖文選單分支一致，reply失敗一律用push備援，避免冷啟動期間reply token
                # 過期時完全沒有任何回覆）
                else:
                    query_spots = detect_query_spots(msg_text)
                    if query_spots:
                        marine = get_marine_data()
                        if marine:
                            p = get_profile(user_id)
                            msg = build_instant_report(query_spots, marine, p)
                        else:
                            msg = "⚠️ 目前無法取得浪況資料，請稍後再試。"
                    else:
                        p = get_profile(user_id)
                        if not p:
                            name = get_line_display_name(user_id)
                            msg = build_no_profile_prompt(name)
                        else:
                            msg = ("找不到對應的浪點或指令 🤔\n"
                                   "輸入 help 查看支援的地區與浪點名稱 👇")

                    if not reply_message(reply_token, msg) and user_id:
                        push_message(user_id, msg)

        except Exception as e:
            print(f"[_process_events 錯誤] event={event.get('type')} err={e}")


# ── 背景排程執行緒 ──────────────
# 每日廣播改由 broadcast.yml（GitHub Actions）主動喚醒 Render 後呼叫 /broadcast-now 觸發，
# 不在這裡排程，避免 Render 剛好醒著時內部排程跟 GitHub Actions 各觸發一次、重複推播。
def _run_scheduler():
    schedule.every(3).hours.do(check_swell_alerts)
    schedule.every(1).hours.do(check_typhoon_alerts)
    print("🕐 排程啟動：每 3h 長浪警戒 / 每 1h 颱風警報（廣播由 broadcast.yml 觸發）")
    while True:
        schedule.run_pending()
        time.sleep(60)


_scheduler_thread = threading.Thread(target=_run_scheduler, daemon=True)
_scheduler_thread.start()


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
