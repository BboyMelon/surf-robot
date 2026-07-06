"""
LINE 圖文選單設定腳本
執行一次即可完成：生成選單圖片 → 上傳 LINE API → 設為預設選單
"""
import json
import math
import requests
from PIL import Image, ImageDraw, ImageFont
from config import LINE_CHANNEL_ACCESS_TOKEN

# ── 選單圖片尺寸（LINE 標準半高選單）───────────────────────
W, H = 2500, 843

# ── 按鈕定義（陽光海洋衝浪風格：海邊日出漸層，藍→青→珊瑚→陽光黃）──
BUTTONS = [
    {"icon": "🔍", "label": "即時浪況查詢",    "top": "#6AC6F2", "bottom": "#0B7DB8", "text_trigger": "🔍 即時浪況查詢"},
    {"icon": "📝", "label": "Surfer 檔案建立",  "top": "#5FE0CE", "bottom": "#00A39A", "text_trigger": "📝 Surfer 檔案建立"},
    {"icon": "📺", "label": "浪況數據與直播資源", "top": "#FFAE8F", "bottom": "#F2604C", "text_trigger": "📺 浪況數據與直播資源"},
    {"icon": "📋", "label": "加入浪況訂閱會員", "top": "#FFDE8A", "bottom": "#FFA62B", "text_trigger": "📋 加入浪況訂閱會員"},
]


def _hex_to_rgb(hex_color: str) -> tuple:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def _draw_vertical_gradient(draw, box, top_hex, bottom_hex) -> None:
    """畫垂直漸層色塊，模擬天空到海面的過渡。"""
    x1, y1, x2, y2 = box
    top_rgb, bottom_rgb = _hex_to_rgb(top_hex), _hex_to_rgb(bottom_hex)
    height = y2 - y1
    for i in range(height):
        ratio = i / height
        r = int(top_rgb[0] + (bottom_rgb[0] - top_rgb[0]) * ratio)
        g = int(top_rgb[1] + (bottom_rgb[1] - top_rgb[1]) * ratio)
        b = int(top_rgb[2] + (bottom_rgb[2] - top_rgb[2]) * ratio)
        draw.line([(x1, y1 + i), (x2, y1 + i)], fill=(r, g, b))


def _draw_wave_band(draw, box, bottom_hex) -> None:
    """在格子底部畫一條淺色波浪剪影，增加衝浪海洋氛圍。"""
    x1, y1, x2, y2 = box
    bottom_rgb = _hex_to_rgb(bottom_hex)
    foam = tuple(min(255, int(c * 0.55 + 255 * 0.45)) for c in bottom_rgb)

    amplitude, wavelength = 14, 160
    baseline = y2 - 34
    points = [(x1, y2)]
    x = x1
    while x <= x2:
        y = baseline + amplitude * math.sin((x - x1) / wavelength * 2 * math.pi)
        points.append((x, y))
        x += 8
    points.append((x2, y2))
    draw.polygon(points, fill=foam)

# 格子位置：左上、右上、左下、右下
CELLS = [
    (0,       0,       W//2, H//2),
    (W//2,    0,       W,    H//2),
    (0,       H//2,    W//2, H),
    (W//2,    H//2,    W,    H),
]


def make_image(path: str = "richmenu.png") -> None:
    img  = Image.new("RGB", (W, H), "#0B7DB8")
    draw = ImageDraw.Draw(img)

    # Apple Color Emoji 是 bitmap-strike 字型，只接受固定像素大小（160 為可用的最大值）
    try:
        font_icon  = ImageFont.truetype("/System/Library/Fonts/Apple Color Emoji.ttc", 160)
    except Exception:
        font_icon  = ImageFont.load_default()

    try:
        font_label = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 80)
        font_sub   = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 52)
    except Exception:
        font_label = ImageFont.load_default()
        font_sub   = font_label

    for i, (btn, cell) in enumerate(zip(BUTTONS, CELLS)):
        x1, y1, x2, y2 = cell
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        inner = (x1 + 4, y1 + 4, x2 - 4, y2 - 4)

        # 天空到海面的漸層色塊 + 底部波浪剪影
        _draw_vertical_gradient(draw, inner, btn["top"], btn["bottom"])
        _draw_wave_band(draw, inner, btn["bottom"])

        # 圖示（embedded_color=True 才能畫出 Apple 彩色 emoji，失敗就跳過）
        try:
            draw.text((cx, cy - 90), btn["icon"], font=font_icon,
                      embedded_color=True, anchor="mm")
        except Exception:
            pass

        # 主標籤（加黑色描邊，避免淡色漸層背景把字吃掉）
        draw.text((cx, cy + 30), btn["label"], font=font_label,
                  fill="white", anchor="mm", stroke_width=4, stroke_fill="black")

        # 副說明
        hint = "點擊查詢"
        draw.text((cx, cy + 120), hint, font=font_sub,
                  fill="#FFFFFF", anchor="mm", stroke_width=2, stroke_fill="black")

    # 格線（白色細線，分隔四格）
    draw.line([(W // 2, 0), (W // 2, H)], fill="#FFFFFF", width=4)
    draw.line([(0, H // 2), (W, H // 2)], fill="#FFFFFF", width=4)

    img.save(path, "PNG")
    print(f"[圖片] 已儲存：{path}")


def create_richmenu() -> str:
    menu = {
        "size": {"width": W, "height": H},
        "selected": True,
        "name": "浪況機器人選單",
        "chatBarText": "📋 開啟選單",
        "areas": [
            {
                "bounds": {"x": CELLS[i][0], "y": CELLS[i][1],
                           "width":  CELLS[i][2] - CELLS[i][0],
                           "height": CELLS[i][3] - CELLS[i][1]},
                "action": {"type": "message", "text": btn["text_trigger"]},
            }
            for i, btn in enumerate(BUTTONS)
        ],
    }
    resp = requests.post(
        "https://api.line.me/v2/bot/richmenu",
        headers={
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        json=menu,
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"建立選單失敗：{resp.status_code} {resp.text}")
    menu_id = resp.json()["richMenuId"]
    print(f"[選單] 已建立：{menu_id}")
    return menu_id


def upload_image(menu_id: str, path: str = "richmenu.png") -> None:
    with open(path, "rb") as f:
        resp = requests.post(
            f"https://api-data.line.me/v2/bot/richmenu/{menu_id}/content",
            headers={
                "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
                "Content-Type": "image/png",
            },
            data=f,
            timeout=30,
        )
    if resp.status_code != 200:
        raise RuntimeError(f"上傳圖片失敗：{resp.status_code} {resp.text}")
    print("[圖片] 已上傳到 LINE")


def set_default(menu_id: str) -> None:
    # 設為所有用戶的預設選單
    resp = requests.post(
        f"https://api.line.me/v2/bot/user/all/richmenu/{menu_id}",
        headers={"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"},
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"設定預設失敗：{resp.status_code} {resp.text}")
    print("[選單] 已設為預設圖文選單 ✅")


def delete_all_existing() -> None:
    """清除舊選單，避免堆積（LINE 免費帳號上限 1000 個）"""
    resp = requests.get(
        "https://api.line.me/v2/bot/richmenu/list",
        headers={"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"},
        timeout=15,
    )
    if resp.status_code != 200:
        return
    for m in resp.json().get("richmenus", []):
        mid = m["richMenuId"]
        requests.delete(
            f"https://api.line.me/v2/bot/richmenu/{mid}",
            headers={"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"},
            timeout=10,
        )
        print(f"[清除] 舊選單 {mid}")


if __name__ == "__main__":
    print("=== LINE 圖文選單設定 ===")
    delete_all_existing()
    make_image()
    menu_id = create_richmenu()
    upload_image(menu_id)
    set_default(menu_id)
    print("\n完成！重新開啟 LINE 對話框即可看到選單。")
