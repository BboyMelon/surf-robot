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
import requests
from flask import Flask, request, abort
from config import LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, SURF_SPOTS_CONFIG, STREAMLIT_URL, get_surf_level
from db import add_member, add_group, save_profile, get_profile, update_display_name
from broadcast import (
    fetch_marine_data, get_marine_data, swell_energy, is_offshore,
    SPOT_STATION_MAP, personal_rating,
    broadcast, check_swell_alerts, check_typhoon_alerts,
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
    "北部": ["金山沙珠灣", "翡翠灣"],
    "宜蘭": ["宜蘭外澳", "烏石港"],
    "中部": ["台中松柏港", "外埔"],
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
        "沙珠灣": "金山沙珠灣", "翡翠灣": "翡翠灣",
        "松柏港": "台中松柏港",
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

        wave_h   = data.get("wave_height", 0.0)
        period   = data.get("wave_period", 0.0)
        wave_dir = data.get("wave_dir", "—")
        wind_dir = data.get("wind_dir", "—")
        wind_spd = data.get("wind_speed", 0.0)

        if wave_h == 0.0 and period == 0.0:
            lines.append(f"📍 {spot_name}\n⚠️ 目前無觀測資料\n")
            continue

        offshore     = is_offshore(wind_dir, cfg.get("offshore_wind", []))
        offshore_tag = "✅ 陸風" if offshore else "❌ 向岸風"
        level        = get_surf_level(wave_h, period)
        energy       = swell_energy(wave_h, period)
        swell_warn   = " ⚠️ 長浪警戒！" if (period > 8 and wave_h > 1.5) else ""

        lines.append(f"📍 {spot_name}")
        lines.append(f"🌊 浪高 {wave_h:.1f}m{swell_warn}｜週期 {period:.1f}s｜{wave_dir}")
        lines.append(f"💨 {wind_dir} {wind_spd:.1f}m/s {offshore_tag}")
        lines.append(f"🏄 GoOcean：{level['label']}")
        lines.append(f"⚡ 湧浪能量：{energy}")

        if profile:
            rating = personal_rating(wave_h, period, profile)
            lines.append(f"👤 {rating}")

        safety = cfg.get("safety_note", "")
        if safety:
            lines.append(f"⚠️ {safety}")
        lines.append("")

    source = marine.get("_meta", {}).get("source", "cwa")
    if source == "open-meteo":
        lines.append("📡 資料：Open-Meteo Marine（模型預報）")
    else:
        lines.append("📡 資料來源：中央氣象署 O-B0075-001")
    return "\n".join(lines)

# ── 加好友歡迎訊息 ────────────────────────────────────────────
def build_welcome(is_group: bool = False) -> str:
    return """🏄‍♂️ 歡迎加入【黃金浪況預報小助手】！
我們會為您精準守候台灣各大浪點，讓您不再錯過起浪好日子！

⏰ 【每日定時報浪時間】
每日 05:00 自動推播最即時、結合 Swell Eye 湧浪能量與 GoOcean 安全評級的精準浪況簡報！

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

    gender     = extract(r"性別[：:]\s*(.+)", text)
    years_raw  = extract(r"浪齡[：:]\s*(\d+)", text)
    board_type = extract(r"(?:版型|衝浪板型)[：:]\s*(.+)", text)
    fav_spots  = extract(r"常衝浪點[：:]\s*(.+)", text)

    surf_years = int(years_raw) if years_raw.isdigit() else 0

    return {
        "gender":     gender,
        "surf_years": surf_years,
        "board_type": board_type,
        "fav_spots":  fav_spots,
    }

# ── 根據 profile 判斷技術等級 ──────────────────────────────────
def skill_label(surf_years: int) -> str:
    if surf_years <= 1:
        return "🌱 新手衝浪者"
    elif surf_years <= 4:
        return "🏄 中級衝浪者"
    else:
        return "🔥 進階衝浪者"

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
性別：（男 / 女 / 其他）
浪齡：（例：3）
版型：（長板 / 短板 / 中長板）
常衝浪點：（填入你常去的浪點）
━━━━━━━━━━━━

建立後每日 05:00 推送專屬浪況早報 🌊"""

# ── 圖文選單：專業海象觀測網 Flex Message ─────────────────
def build_ocean_links_flex() -> dict:
    return {
        "type": "flex",
        "altText": "📚 專業海象觀測網",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#0D4F8C",
                "contents": [{
                    "type": "text",
                    "text": "🌊 精選海象觀測資源",
                    "color": "#ffffff",
                    "weight": "bold",
                    "size": "lg",
                }],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#1a5fa8",
                        "action": {
                            "type": "uri",
                            "label": "🌊 中央氣象署 CWA 海象資訊",
                            "uri": "https://ocean.cwb.gov.tw/",
                        },
                    },
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#0A6B5E",
                        "action": {
                            "type": "uri",
                            "label": "🔬 國家海洋研究院 NODASS",
                            "uri": "https://nodass.namr.gov.tw/",
                        },
                    },
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#C45D00",
                        "action": {
                            "type": "uri",
                            "label": "🏄 Swell Eye 衝浪科學",
                            "uri": "https://www.surf-forecast.com/",
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
性別：（男 / 女 / 其他）
浪齡：（例：3）
版型：（長板 / 短板 / 中長板）
常衝浪點：（填入你常去的浪點）
━━━━━━━━━━━━

{spot_menu}"""

# ── 回覆確認訊息 ──────────────────────────────────────────────
def build_profile_confirm(profile: dict) -> str:
    label = skill_label(profile.get("surf_years", 0))
    return f"""✅ 衝浪檔案建立完成！

👤 性別：{profile.get('gender', '未填')}
🏄 浪齡：{profile.get('surf_years', 0)} 年
🛹 板型：{profile.get('board_type', '未填')}
📍 常衝浪點：{profile.get('fav_spots', '未填')}
⭐ 等級判定：{label}

從明天起每日 05:00 我會依照你的程度
推送專屬客製化浪況早報給你！🌊

隨時回傳新的資料可以更新你的衝浪檔案 🤙"""

# ── LINE 簽章驗證 ─────────────────────────────────────────────
def verify_signature(body: bytes, signature: str) -> bool:
    secret = LINE_CHANNEL_SECRET.encode("utf-8")
    hash_val = hmac.new(secret, body, hashlib.sha256).digest()
    expected = base64.b64encode(hash_val).decode("utf-8")
    return hmac.compare_digest(expected, signature)

# ── 取得 LINE 顯示名稱 ────────────────────────────────────────
def get_line_display_name(user_id: str) -> str:
    url = f"https://api.line.me/v2/bot/profile/{user_id}"
    headers = {"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("displayName", user_id)
    except Exception:
        pass
    return user_id

# ── 推送訊息 ──────────────────────────────────────────────────
def push_message(to: str, text: str) -> None:
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"to": to, "messages": [{"type": "text", "text": text}]}
    resp = requests.post(url, headers=headers, json=payload, timeout=10)
    if resp.status_code != 200:
        print(f"[Push 失敗] {resp.status_code} {resp.text}")

# ── Reply Flex Message ────────────────────────────────────────
def reply_flex(reply_token: str, flex: dict) -> None:
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"replyToken": reply_token, "messages": [flex]}
    requests.post(url, headers=headers, json=payload, timeout=10)

# ── Reply Message ─────────────────────────────────────────────
def reply_message(reply_token: str, text: str) -> None:
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}],
    }
    requests.post(url, headers=headers, json=payload, timeout=10)

# ── Health Check ─────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return "OK", 200

# ── Webhook 主路由 ────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data()

    if not verify_signature(body, signature):
        abort(400, "Invalid signature")

    events = request.json.get("events", [])

    for event in events:
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

        # ── 機器人加入群組 ────────────────────────────────────
        elif event_type == "join" and source_type == "group":
            group_id = source.get("groupId")
            add_group(group_id)
            push_message(group_id, build_welcome(is_group=True))
            print(f"[Join] {group_id}")

        # ── 文字訊息處理 ──────────────────────────────────────
        elif event_type == "message" and event.get("message", {}).get("type") == "text":
            msg_text = event["message"]["text"]
            user_id  = source.get("userId", "")

            # 每次互動自動更新 LINE 顯示名稱
            if user_id:
                display_name = get_line_display_name(user_id)
                update_display_name(user_id, display_name)

            # ── 圖文選單觸發 ──────────────────────────────────
            if "🔍 即時浪況查詢" in msg_text:
                reply_message(reply_token, SPOT_QUERY_HINT)

            elif "📝 Surfer 檔案建立" in msg_text:
                reply_message(reply_token, PROFILE_FORM)

            elif "📚 專業海象觀測網" in msg_text:
                reply_flex(reply_token, build_ocean_links_flex())

            elif "🗺️ Windy 動態地圖" in msg_text:
                reply_message(reply_token,
                    f"🗺️ Windy 動態地圖\n\n點擊下方連結，查看台灣即時浪高與湧浪粒子動圖 👇\n{STREAMLIT_URL}")

            # 查詢自己名稱
            elif any(k in msg_text for k in ["我的ID", "我的id", "my id", "ID是", "我的名稱"]):
                name = get_line_display_name(user_id)
                reply_message(reply_token, f"你好，{name}！\n你的 LINE 名稱是：{name}")

            # 填寫/更新 Profile
            elif "性別" in msg_text and "浪齡" in msg_text:
                profile = parse_profile(msg_text)
                if profile and user_id:
                    save_profile(user_id, profile)
                    reply_message(reply_token, build_profile_confirm(profile))
                    print(f"[Profile 儲存] {user_id} → {profile}")
                else:
                    reply_message(reply_token, "格式好像有點問題 🤔\n請參考範例重新填寫喔！")

            # 查詢自己的 Profile
            elif any(k in msg_text for k in ["我的資料", "我的檔案", "查詢資料"]):
                p = get_profile(user_id)
                if p:
                    reply_message(reply_token, build_profile_confirm(p))
                else:
                    reply_message(reply_token, build_no_profile_prompt())

            # 其餘訊息：先嘗試浪點查詢，否則引導未建檔用戶填資料
            else:
                query_spots = detect_query_spots(msg_text)
                if query_spots:
                    marine = get_marine_data()
                    if marine:
                        p = get_profile(user_id)
                        reply_message(reply_token, build_instant_report(query_spots, marine, p))
                    else:
                        reply_message(reply_token, "⚠️ 目前無法取得浪況資料，請稍後再試。")
                else:
                    p = get_profile(user_id)
                    if not p:
                        name = get_line_display_name(user_id)
                        reply_message(reply_token, build_no_profile_prompt(name))

    return "OK", 200


# ── 背景排程執行緒（Render 上唯一跑排程的地方）──────────────
def _run_scheduler():
    schedule.every().day.at("05:00").do(broadcast)
    schedule.every(3).hours.do(check_swell_alerts)
    schedule.every(1).hours.do(check_typhoon_alerts)
    print("🕐 排程啟動：每日 05:00 廣播 / 每 3h 長浪警戒 / 每 1h 颱風警報")
    while True:
        schedule.run_pending()
        time.sleep(60)


_scheduler_thread = threading.Thread(target=_run_scheduler, daemon=True)
_scheduler_thread.start()


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
