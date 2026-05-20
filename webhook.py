"""
LINE Webhook 監聽伺服器 — Flask
處理：JoinEvent / FollowEvent / 使用者 Profile 填寫解析
"""
import re
import hashlib
import hmac
import base64
import requests
from flask import Flask, request, abort
from config import LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, SURF_SPOTS_CONFIG
from db import add_member, add_group, save_profile, get_profile

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

# ── 加好友歡迎訊息 ────────────────────────────────────────────
def build_welcome(is_group: bool = False) -> str:
    spot_menu = build_spot_menu()
    intro = "歡迎加入 🌊 浪況小助手！" if is_group else "嗨！歡迎使用 🌊 浪況小助手！"
    return f"""{intro}

我是你的專屬衝浪教練 🏄
填寫個人資料後，我會根據你的程度提供量身訂製的浪況建議！

請複製以下格式，填寫後直接回傳給我 👇

━━━━━━━━━━━━
性別：（男 / 女 / 其他）
浪齡：（例：3）
衝浪板型：（長板 / 短板 / 中長板）
常衝浪點：（填入你常去的浪點）
━━━━━━━━━━━━

{spot_menu}

填完後我立刻幫你建立衝浪檔案 🤙
每日早上 06:00 推送專屬浪況早報 🌊"""

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
    board_type = extract(r"衝浪板型[：:]\s*(.+)", text)
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

# ── 回覆確認訊息 ──────────────────────────────────────────────
def build_profile_confirm(profile: dict) -> str:
    label = skill_label(profile.get("surf_years", 0))
    return f"""✅ 衝浪檔案建立完成！

👤 性別：{profile.get('gender', '未填')}
🏄 浪齡：{profile.get('surf_years', 0)} 年
🛹 板型：{profile.get('board_type', '未填')}
📍 常衝浪點：{profile.get('fav_spots', '未填')}
⭐ 等級判定：{label}

從明天起每日 06:00 我會依照你的程度
推送專屬客製化浪況早報給你！🌊

隨時回傳新的資料可以更新你的衝浪檔案 🤙"""

# ── LINE 簽章驗證 ─────────────────────────────────────────────
def verify_signature(body: bytes, signature: str) -> bool:
    secret = LINE_CHANNEL_SECRET.encode("utf-8")
    hash_val = hmac.new(secret, body, hashlib.sha256).digest()
    expected = base64.b64encode(hash_val).decode("utf-8")
    return hmac.compare_digest(expected, signature)

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

            # 查詢自己 ID
            if any(k in msg_text for k in ["我的ID", "我的id", "my id", "ID是"]):
                reply_message(reply_token, f"你的 LINE User ID 是：\n{user_id}")

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
                    reply_message(reply_token, "還沒有你的衝浪檔案喔！\n請填寫個人資料讓我認識你 🏄")

    return "OK", 200

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
