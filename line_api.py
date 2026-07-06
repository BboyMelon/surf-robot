"""
共用 LINE Messaging API 呼叫邏輯（push / reply / 取得顯示名稱）。
原本 webhook.py 跟 broadcast.py 各自寫了一份幾乎一樣的 requests.post 邏輯，
這裡統一成一份，順便讓所有呼叫都一致地檢查回應狀態並記 log。
"""
import requests
from config import LINE_CHANNEL_ACCESS_TOKEN

_HEADERS = {
    "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    "Content-Type": "application/json",
}


def _post(url: str, payload: dict) -> bool:
    try:
        resp = requests.post(url, headers=_HEADERS, json=payload, timeout=10)
        if resp.status_code != 200:
            print(f"[LINE API 失敗] {url} {resp.status_code} {resp.text}")
        return resp.status_code == 200
    except Exception as e:
        print(f"[LINE API 例外] {url} err={e}")
        return False


def push_text(to: str, text: str) -> bool:
    return _post(
        "https://api.line.me/v2/bot/message/push",
        {"to": to, "messages": [{"type": "text", "text": text}]},
    )


def reply_text(reply_token: str, text: str) -> bool:
    return _post(
        "https://api.line.me/v2/bot/message/reply",
        {"replyToken": reply_token, "messages": [{"type": "text", "text": text}]},
    )


def reply_flex(reply_token: str, flex: dict) -> bool:
    return _post(
        "https://api.line.me/v2/bot/message/reply",
        {"replyToken": reply_token, "messages": [flex]},
    )


def push_flex(to: str, flex: dict) -> bool:
    return _post(
        "https://api.line.me/v2/bot/message/push",
        {"to": to, "messages": [flex]},
    )


def get_display_name(user_id: str) -> str:
    url = f"https://api.line.me/v2/bot/profile/{user_id}"
    headers = {"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("displayName", user_id)
    except Exception:
        pass
    return user_id
