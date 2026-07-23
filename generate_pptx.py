#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
根據 PRESENTATION_OUTLINE.md 產生可編輯的 LINE 浪況機器人簡報 (.pptx)
執行一次即可產出 surf_robot_簡報.pptx，可用 PowerPoint / Keynote / Google Slides 開啟編輯，
也可在 PowerPoint 用「檔案 > 匯出 > 建立 PDF/XPS」轉成 PDF。
"""

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn

# ---------- 色彩系統 ----------
NAVY = RGBColor(0x0D, 0x2A, 0x4A)      # 主背景（比大綱建議略深，內文更好讀）
BLUE = RGBColor(0x0D, 0x4F, 0x8C)      # 主色
LIGHT_BLUE = RGBColor(0x6A, 0xC6, 0xF2)  # 淺藍（標籤/次標題）
CORAL = RGBColor(0xF2, 0x60, 0x4C)     # 珊瑚紅（重點/警示）
WHITE = RGBColor(0xF5, 0xF7, 0xFA)
PANEL = RGBColor(0x14, 0x3A, 0x63)     # 內容面板底色（比背景稍亮，做層次）
DARK_TEXT = RGBColor(0x14, 0x1B, 0x24)

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)

prs = Presentation()
prs.slide_width = SLIDE_W
prs.slide_height = SLIDE_H
BLANK = prs.slide_layouts[6]


def add_slide():
    slide = prs.slides.add_slide(BLANK)
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, SLIDE_H)
    bg.fill.solid()
    bg.fill.fore_color.rgb = NAVY
    bg.line.fill.background()
    bg.shadow.inherit = False
    # 底部細條裝飾
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, SLIDE_H - Inches(0.12), SLIDE_W, Inches(0.12))
    bar.fill.solid()
    bar.fill.fore_color.rgb = CORAL
    bar.line.fill.background()
    bar.shadow.inherit = False
    return slide


def set_font(run, size=18, color=WHITE, bold=False, name="Microsoft JhengHei", italic=False):
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.font.bold = bold
    run.font.italic = italic
    run.font.name = name


def add_title(slide, text, y=Inches(0.35), size=32, tag=None):
    if tag:
        tag_box = slide.shapes.add_textbox(Inches(0.6), y, Inches(6), Inches(0.4))
        tf = tag_box.text_frame
        p = tf.paragraphs[0]
        r = p.add_run()
        r.text = tag
        set_font(r, size=14, color=LIGHT_BLUE, bold=True)
        y = y + Inches(0.4)
    box = slide.shapes.add_textbox(Inches(0.6), y, Inches(12.1), Inches(0.9))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = text
    set_font(r, size=size, color=WHITE, bold=True)
    # 標題底線
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.6), y + Inches(0.85), Inches(1.4), Pt(3))
    line.fill.solid()
    line.fill.fore_color.rgb = CORAL
    line.line.fill.background()
    line.shadow.inherit = False
    return y + Inches(1.1)


def add_panel(slide, x, y, w, h):
    panel = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    panel.fill.solid()
    panel.fill.fore_color.rgb = PANEL
    panel.line.color.rgb = BLUE
    panel.line.width = Pt(0.75)
    panel.shadow.inherit = False
    try:
        panel.adjustments[0] = 0.04
    except Exception:
        pass
    return panel


def add_bullets(slide, items, x, y, w, h, size=16, mono=False, line_spacing=1.15):
    box = slide.shapes.add_textbox(x + Inches(0.15), y + Inches(0.1), w - Inches(0.3), h - Inches(0.2))
    tf = box.text_frame
    tf.word_wrap = True
    first = True
    for item in items:
        if isinstance(item, tuple):
            text, level = item
        else:
            text, level = item, 0
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.space_after = Pt(6)
        p.line_spacing = line_spacing
        p.level = min(level, 4)
        r = p.add_run()
        bullet = "" if mono else ("● " if level == 0 else "‒ ")
        r.text = f"{bullet}{text}"
        color = LIGHT_BLUE if (text.strip().startswith(("✅", "🟢")) and not mono) else WHITE
        if "❌" in text:
            color = CORAL
        set_font(r, size=size, color=color,
                  name="Consolas" if mono else "Microsoft JhengHei",
                  bold=(level == 0 and not mono))
    return box


def add_table(slide, headers, rows, x, y, w, h, header_size=14, body_size=13, col_widths=None):
    n_rows = len(rows) + 1
    n_cols = len(headers)
    gtable = slide.shapes.add_table(n_rows, n_cols, x, y, w, h).table
    if col_widths:
        for i, cw in enumerate(col_widths):
            gtable.columns[i].width = cw
    for j, htext in enumerate(headers):
        cell = gtable.cell(0, j)
        cell.text = htext
        cell.fill.solid()
        cell.fill.fore_color.rgb = BLUE
        for p in cell.text_frame.paragraphs:
            p.alignment = PP_ALIGN.CENTER
            for r in p.runs:
                set_font(r, size=header_size, color=WHITE, bold=True)
    for i, row in enumerate(rows, start=1):
        for j, val in enumerate(row):
            cell = gtable.cell(i, j)
            cell.text = str(val)
            cell.fill.solid()
            cell.fill.fore_color.rgb = PANEL if i % 2 == 1 else NAVY
            for p in cell.text_frame.paragraphs:
                p.alignment = PP_ALIGN.LEFT if j == 0 else PP_ALIGN.LEFT
                for r in p.runs:
                    set_font(r, size=body_size, color=WHITE)
    return gtable


def content_slide(tag, title, bullets, mono=False, size=17):
    slide = add_slide()
    y = add_title(slide, title, tag=tag)
    add_panel(slide, Inches(0.6), y, Inches(12.1), Inches(7.5) - y - Inches(0.4))
    add_bullets(slide, bullets, Inches(0.6), y, Inches(12.1), Inches(7.5) - y - Inches(0.4), size=size, mono=mono)
    return slide


def table_slide(tag, title, headers, rows, note=None, col_widths=None):
    slide = add_slide()
    y = add_title(slide, title, tag=tag)
    table_h = Inches(4.6) if note else Inches(5.2)
    add_table(slide, headers, rows, Inches(0.6), y, Inches(12.1), table_h, col_widths=col_widths)
    if note:
        add_bullets(slide, [note], Inches(0.6), y + table_h + Inches(0.1), Inches(12.1), Inches(1.0), size=15)
    return slide


# =========================================================
# SLIDE 01｜封面
# =========================================================
slide = add_slide()
title_box = slide.shapes.add_textbox(Inches(0.8), Inches(2.4), Inches(11.7), Inches(1.3))
tf = title_box.text_frame
tf.word_wrap = True
p = tf.paragraphs[0]
r = p.add_run()
r.text = "🌊 LINE 浪況自動推播機器人"
set_font(r, size=44, color=WHITE, bold=True)

sub_box = slide.shapes.add_textbox(Inches(0.8), Inches(3.6), Inches(11.7), Inches(0.8))
tf = sub_box.text_frame
tf.word_wrap = True
p = tf.paragraphs[0]
r = p.add_run()
r.text = "結合 CWA 浮標 API × LINE Messaging × 衝浪科學的智慧推播系統"
set_font(r, size=20, color=LIGHT_BLUE)

info_box = slide.shapes.add_textbox(Inches(0.8), Inches(6.3), Inches(11.7), Inches(0.6))
tf = info_box.text_frame
p = tf.paragraphs[0]
r = p.add_run()
r.text = "作者姓名 ／ 課程名稱 ／ 日期（請自行填寫）"
set_font(r, size=16, color=WHITE, italic=True)

line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(3.35), Inches(2), Pt(3))
line.fill.solid(); line.fill.fore_color.rgb = CORAL; line.line.fill.background(); line.shadow.inherit = False

# =========================================================
# SLIDE 02｜目錄
# =========================================================
slide = add_slide()
y = add_title(slide, "目錄", tag="AGENDA")
agenda = [
    "1. 問題背景與動機", "2. 系統功能展示", "3. 系統架構設計",
    "4. 資料來源與容錯機制", "5. 浪況評分邏輯", "6. LINE 整合技術",
    "7. 推播排程設計", "8. 開發挑戰與解決方案", "9. 成果與未來規劃",
]
col_w = Inches(5.85)
add_panel(slide, Inches(0.6), y, col_w, Inches(4.6))
add_panel(slide, Inches(6.85), y, col_w, Inches(4.6))
add_bullets(slide, agenda[:5], Inches(0.6), y, col_w, Inches(4.6), size=20)
add_bullets(slide, agenda[5:], Inches(6.85), y, col_w, Inches(4.6), size=20)

# =========================================================
# SLIDE 03｜問題背景
# =========================================================
slide = add_slide()
y = add_title(slide, "衝浪者每天面對的痛點", tag="PART 1 ｜ 問題背景")
add_panel(slide, Inches(0.6), y, Inches(12.1), Inches(3.6))
add_bullets(slide, [
    "📍 台灣有 15+ 個主要衝浪浪點",
    "🔍 資訊分散在 CWA、GoOcean、Windy 等多個網站",
    "📱 每天要手動查詢、沒有個人化建議",
    "⚠️ 看不懂氣象術語的衝浪者容易誤判安全性",
    "流程：用戶 → 打開 CWA → 打開 GoOcean → 打開 Windy → 自己判斷（太繁瑣）",
], Inches(0.6), y, Inches(12.1), Inches(3.6), size=19)

quote_panel = add_panel(slide, Inches(0.6), y + Inches(3.8), Inches(12.1), Inches(1.1))
qbox = slide.shapes.add_textbox(Inches(0.9), y + Inches(3.95), Inches(11.5), Inches(0.8))
tf = qbox.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]
r = p.add_run()
r.text = "「能不能讓機器人每天早上主動告訴我：今天能不能衝？去哪裡最好？」"
set_font(r, size=20, color=CORAL, bold=True, italic=True)

# =========================================================
# SLIDE 04｜解決方案定位
# =========================================================
table_slide(
    "PART 1 ｜ 解決方案", "打造衝浪者的私人氣象教練",
    ["傳統做法", "本系統", "升級效果"],
    [
        ["手動查網站", "自動推播", "省時、不遺漏"],
        ["看數字", "看星號＋燈號", "一眼懂"],
        ["通用資訊", "依浪齡個人化", "初學者不冒險"],
        ["等到了才知道", "長浪警戒主動通知", "提前準備"],
    ],
)

# =========================================================
# SLIDE 05｜功能展示
# =========================================================
slide = add_slide()
y = add_title(slide, "機器人可以做什麼？", tag="PART 2 ｜ 功能展示")
add_panel(slide, Inches(0.6), y, Inches(12.1), Inches(5.2))
add_bullets(slide, [
    "📢 每日 05:00 / 15:00 自動廣播",
    "🔍 輸入地名即時查詢浪況",
    "🏆 今日最佳浪點前三名推薦",
    "⚠️ 大浪 / 颱風自動警戒通知",
    "📺 一鍵查 YouTube 浪況直播（北/東/南共20支）",
    "👤 建立個人 Surfer 檔案（浪齡/板型/常去浪點）",
    "🌙 單點查詢自動附上今日潮汐時刻",
    "",
    "💡 建議於此處插入 Demo 截圖：早報推播訊息 / 最佳浪點推薦 / 圖文選單 + Flex 卡片",
], Inches(0.6), y, Inches(12.1), Inches(5.2), size=19)

# =========================================================
# SLIDE 06｜整體系統架構圖
# =========================================================
slide = add_slide()
y = add_title(slide, "系統架構總覽", tag="PART 3 ｜ 技術設計")
add_panel(slide, Inches(0.6), y, Inches(12.1), Inches(4.3))
diagram = """┌────────────────┐     ┌───────────────────────┐     ┌────────────────┐
│    資料來源     │ ──▶ │    Render 伺服器       │ ──▶ │    使用者端     │
│                │     │                       │     │                │
│ CWA 浮標 API    │     │ broadcast.py          │     │ LINE App       │
│ Open-Meteo     │     │ webhook.py            │     │                │
│ CWA 潮汐 API    │     │ line_api.py           │     └────────────────┘
│ CWA 颱風 API    │     │ db.py                 │
└────────────────┘     └──────────┬────────────┘
                                   │
                  ┌────────────────┼────────────────┐
                  ▼                ▼                ▼
             Supabase          LINE API        GitHub Actions
             (資料庫)          (推播/回覆)       (定時排程)"""
add_bullets(slide, [diagram], Inches(0.6), y, Inches(12.1), Inches(4.3), size=14, mono=True, line_spacing=1.0)
foot = slide.shapes.add_textbox(Inches(0.6), y + Inches(4.45), Inches(12.1), Inches(0.5))
tf = foot.text_frame
p = tf.paragraphs[0]
r = p.add_run(); r.text = "共 5 個核心模組、4 個外部服務、4 個 GitHub Actions 工作流程"
set_font(r, size=16, color=LIGHT_BLUE, bold=True)

# =========================================================
# SLIDE 07｜技術選型
# =========================================================
table_slide(
    "PART 3 ｜ 技術設計", "為什麼選這些技術？",
    ["技術", "選擇理由", "替代方案比較"],
    [
        ["Python Flask", "輕量 Webhook 伺服器，Render 原生支援 gunicorn", "Django（太重）"],
        ["LINE API", "台灣用戶覆蓋率 >90%，支援 Push/Flex/圖文選單", "Telegram、FB Messenger"],
        ["CWA API", "台灣官方浮標，即時波高/週期/風向，免費", "無同等品質的替代品"],
        ["Supabase", "免費雲端 PostgreSQL，Render 重啟資料不消失", "Firebase（較貴）／本機 SQLite（不持久）"],
        ["GitHub Actions", "免費 CI/CD + 定時任務，不受 Render 睡眠影響", "Render 付費 Cron Job"],
    ],
    col_widths=[Inches(2.6), Inches(6.0), Inches(3.5)],
)

# =========================================================
# SLIDE 08｜資料來源設計
# =========================================================
slide = add_slide()
y = add_title(slide, "CWA 浮標 API × Open-Meteo 備援策略", tag="PART 3 ｜ 資料來源")
add_panel(slide, Inches(0.6), y, Inches(12.1), Inches(5.2))
add_bullets(slide, [
    "主要來源：CWA O-B0075-001",
    ("10 個浮標站（台灣北/中/東/南/離島），即時波高、週期、風向、海溫、潮位", 1),
    ("每小時更新，但有時整批卡住", 1),
    "備援來源：Open-Meteo Marine API",
    ("全球免費、不需 API Key，任何 IP 都能存取", 1),
    ("解決 CWA 有時限制特定 IP 的問題；無海溫、無潮位", 1),
    "資料決策流程：CWA 全部有效 → 用 CWA｜CWA 部分缺站 → CWA + Open-Meteo 補缺｜CWA 全失效 → 完全切換 Open-Meteo",
    "⚠️ 重要設計：新鮮度檢查（>3 小時視為失效）— 颱風期間 CWA 可能 48 小時未更新，若不檢查會推播錯誤的平靜假象",
], Inches(0.6), y, Inches(12.1), Inches(5.2), size=17)

# =========================================================
# SLIDE 09｜GoOcean 安全分級
# =========================================================
table_slide(
    "PART 3 ｜ 浪況評分邏輯（一）", "看懂浪況：GoOcean 安全燈號",
    ["燈號", "條件", "說明"],
    [
        ["🟢 初學", "浪高 < 0.8m", "安全，適合新手"],
        ["🟡 中階", "浪高 ≥0.8m 或（浪高≥0.5m 且週期≥9s）", "有一定挑戰"],
        ["🔴 進階", "浪高 ≥1.8m 或（浪高≥1.0m 且週期≥12s）", "需要技術"],
        ["⛔ 危險", "浪高 ≥3.0m 或（浪高≥2.0m 且週期≥12s）", "禁止入水"],
    ],
    note="關鍵設計：用 OR 邏輯而非 AND — 同樣 1.0m 的浪，週期 12s 的能量和衝擊力遠大於週期 5s；長週期湧浪（Ground Swell）危險性不能只靠浪高判斷",
    col_widths=[Inches(2.0), Inches(6.5), Inches(3.6)],
)

# =========================================================
# SLIDE 10｜品質分數×星號
# =========================================================
slide = add_slide()
y = add_title(slide, "衝浪品質 ≠ 浪高：週期才是關鍵", tag="PART 3 ｜ 浪況評分邏輯（二）")
add_panel(slide, Inches(0.6), y, Inches(12.1), Inches(5.2))
add_bullets(slide, [
    "品質分數公式：品質分數 = 浪高(m) × 週期(s) × 週期品質係數",
    "週期品質係數：",
    ("<7s → ×0.7　短週期風浪（Wind Swell）：雜亂、打板", 1),
    ("7–9s → ×1.0　一般混合浪", 1),
    ("9–12s → ×1.3　長週期混合浪", 1),
    ("≥12s → ×1.6　Ground Swell（湧浪）：乾淨有力，最佳品質", 1),
    "實際案例對比（同樣浪高 1.0m）：",
    ("週期 6s（風浪）：1.0 × 6 × 0.7 = 4.2 分 ⭐⭐", 1),
    ("週期 12s（湧浪）：1.0 × 12 × 1.6 = 19.2 分 ⭐⭐⭐⭐⭐ → 相差 4.6 倍", 1),
    "陸風加成：當天吹陸風（離岸風）→ 分數 ×1.3（把浪梳理成乾淨立牆，大幅提升浪形品質）",
], Inches(0.6), y, Inches(12.1), Inches(5.2), size=16)

# =========================================================
# SLIDE 11｜Webhook 非同步機制
# =========================================================
slide = add_slide()
y = add_title(slide, "Webhook 為什麼要非同步？", tag="PART 3 ｜ LINE 整合")
add_panel(slide, Inches(0.6), y, Inches(6.9), Inches(5.2))
add_bullets(slide, [
    "問題：",
    ("查詢浪況需呼叫外部 API，可能等待 2–8 秒", 1),
    ("LINE 要求 Webhook 必須在 1 秒內回應 HTTP 200", 1),
    ("同步等待 → LINE 誤以為失敗 → 重送事件 → 重複推播", 1),
    "解法：先回 200，事件處理丟背景執行緒",
    "額外防護：",
    ("reply_token 過期（Render 重啟中）時，reply_message() 失敗 → 自動改 push_message() 補送", 1),
], Inches(0.6), y, Inches(6.9), Inches(5.2), size=16)
add_panel(slide, Inches(7.7), y, Inches(5.0), Inches(5.2))
flow = "LINE 發 Webhook\n     │\n     ▼\nFlask 立即回 200 ◀ (<10ms)\n     │  (同時)\n     ▼\n背景執行緒：\n查API → 建訊息\n → 推播給用戶"
add_bullets(slide, [flow], Inches(7.7), y, Inches(5.0), Inches(5.2), size=15, mono=True, line_spacing=1.1)

# =========================================================
# SLIDE 12｜圖文選單製作原理
# =========================================================
slide = add_slide()
y = add_title(slide, "Rich Menu：圖片 × 按鈕分開設計", tag="PART 3 ｜ LINE 整合")
add_panel(slide, Inches(0.6), y, Inches(12.1), Inches(5.2))
add_bullets(slide, [
    "一般人的誤解：「圖片上的按鈕就是按鈕」；實際上圖片和按鈕座標完全分開定義",
    "圖片（視覺層）：",
    ("Python Pillow 直接用程式繪製，2500×843 像素", 1),
    ("漸層色塊（逐行填色模擬漸層）", 1),
    ("Apple Color Emoji 彩色字型渲染 emoji，文字黑色描邊避免淡色背景吃字", 1),
    "按鈕（行為層）：",
    ("POST 給 LINE API 的 JSON：areas[] = 每格 x/y 座標 + 動作", 1),
    ("action.type = \"message\"，action.text = 觸發文字", 1),
    "流程：用戶點擊左下格 → LINE 自動發出觸發文字 → Webhook 收到 → 回傳 Flex Carousel",
], Inches(0.6), y, Inches(12.1), Inches(5.2), size=17)

# =========================================================
# SLIDE 13｜推播排程設計
# =========================================================
slide = add_slide()
y = add_title(slide, "免費伺服器的挑戰：Render Free Tier 睡眠機制", tag="PART 3 ｜ 推播排程設計")
add_panel(slide, Inches(0.6), y, Inches(12.1), Inches(5.2))
add_bullets(slide, [
    "問題：Render 免費方案 15 分鐘無請求 → 進入睡眠；冷啟動 30–60 秒 → 廣播時間到了服務還在睡 → 廣播失敗",
    "解法：GitHub Actions 作為外部可靠定時器",
    ("broadcast.yml：每 5 秒 curl /health，等服務醒來（最多 2 分鐘）→ POST /broadcast-now 觸發廣播", 1),
    ("keep_alive.yml：高峰時段每 5 分鐘 ping，避免睡眠", 1),
    "設計取捨：保活時段只開台灣 05:00–10:00、14:00–20:00，非高峰時段放它睡 → 節省免費額度，避免月底被強制停權",
], Inches(0.6), y, Inches(12.1), Inches(5.2), size=17)

# =========================================================
# SLIDE 14｜開發挑戰（一）SSL 憑證問題
# =========================================================
slide = add_slide()
y = add_title(slide, "最難排查的 Bug：Render 上的 SSL 憑證失敗", tag="PART 4 ｜ 開發挑戰")
add_panel(slide, Inches(0.6), y, Inches(12.1), Inches(5.2))
add_bullets(slide, [
    "症狀：本機測試完全正常，Deploy 到 Render 後 CWA API 呼叫全部失敗（SSLError: Missing Subject Key Identifier）",
    "排查過程：",
    ("❌ 以為是 API Key 問題 → 輪替金鑰 → 沒用", 1),
    ("❌ 加 requests.get(verify=False) → 仍失敗（問題在更底層）", 1),
    ("❌ 自訂 ssl.SSLContext → 仍失敗（Python ssl 模組的限制）", 1),
    ("✅ 改用系統 curl -sk 子行程 → 成功！", 1),
    "根本原因：CWA 憑證缺少 Subject Key Identifier 欄位（輕微不合規）。本機 macOS OpenSSL 不嚴格檢查，Render 容器 OpenSSL 3.2+ 直接拒絕，Python 層根本沒機會處理",
    "學習：除錯時要辨清問題發生在哪一層，不要從症狀猜原因",
], Inches(0.6), y, Inches(12.1), Inches(5.2), size=17)

# =========================================================
# SLIDE 15｜開發挑戰（二）颱風資料過期 Bug
# =========================================================
slide = add_slide()
y = add_title(slide, "颱風天機器人還在推薦「適合衝浪」", tag="PART 4 ｜ 開發挑戰")
add_panel(slide, Inches(0.6), y, Inches(12.1), Inches(5.2))
add_bullets(slide, [
    "事件：颱風米克拉（距台 410km）期間",
    "症狀：機器人推播浪況 0.3–1.3m 🟢初學，實際海況 1.2–2.8m 🔴進階（用 Open-Meteo 驗證）",
    "根本原因：CWA 整批浮標資料卡在 45 小時前沒更新，程式沒有檢查資料時間戳記，機器人把颱風前的平靜假象當成即時資料",
    "修復方式：新增 MARINE_DATA_MAX_AGE_HOURS = 3，超過 3 小時的資料視為失效 → 觸發 Open-Meteo 備援",
    "影響範圍：長浪警戒共用同一資料源，颱風期間該發的警戒也一起修復",
    "學習：資料的「時效性」跟「存在性」同樣重要",
], Inches(0.6), y, Inches(12.1), Inches(5.2), size=18)

# =========================================================
# SLIDE 16｜系統成果
# =========================================================
slide = add_slide()
y = add_title(slide, "目前系統狀態", tag="PART 5 ｜ 成果與未來")
col_w = Inches(3.95)
add_panel(slide, Inches(0.6), y, col_w, Inches(5.2))
add_panel(slide, Inches(4.7), y, col_w, Inches(5.2))
add_panel(slide, Inches(8.8), y, col_w, Inches(5.2))
add_bullets(slide, [
    "核心推播", ("15 大浪點，每日 05:00/15:00 廣播", 1),
    ("個人化推播（浪齡/板型/常去浪點）", 1),
    ("今日最佳浪點前三名", 1),
    ("長浪警戒（自動偵測 Ground Swell）", 1),
    ("颱風通知（1000km 範圍內）", 1),
], Inches(0.6), y, col_w, Inches(5.2), size=15)
add_bullets(slide, [
    "互動查詢", ("浪點/地區查詢 + 今日潮汐時刻", 1),
    ("全台 15 浪點總覽", 1),
    ("明日浪況預報（7天模型）", 1),
    ("YouTube 直播快速入口（20支）", 1),
], Inches(4.7), y, col_w, Inches(5.2), size=15)
add_bullets(slide, [
    "技術指標", ("Webhook 回應 <10ms（非同步化後）", 1),
    ("API 重試機制：失敗自動重試 3 次", 1),
    ("資料備援：CWA + Open-Meteo 混合", 1),
    ("警戒 de-dup 存 DB，Render 重啟不重置", 1),
], Inches(8.8), y, col_w, Inches(5.2), size=15)

# =========================================================
# SLIDE 17｜未來規劃
# =========================================================
slide = add_slide()
y = add_title(slide, "下一步要做什麼？", tag="PART 5 ｜ 成果與未來")
row_h = Inches(1.55)
labels = [("短期（可實作）", CORAL), ("中期（技術升級）", LIGHT_BLUE), ("長期（商業化）", WHITE)]
items = [
    ["🏄 find_best_spots() 加入潮汐因子 → 滿潮前後 2 小時浪形更好，加乘排序",
     "📹 浪友影片投稿 → 傳「📹 烏石港 https://...」自動存入 surf_videos 表，廣播底部附上今日直播/影片"],
    ["📊 Flex Message 廣播 → 目前純文字，改成圖文卡片更直覺",
     "🌐 Windguru 資料整合 → 精準湧浪模型，補足 CWA 沒有的浪向細節"],
    ["💰 訂閱制：免費 1 次/天，進階解鎖即時查詢無限次",
     "🤝 與衝浪學校合作：學員管理 + 課程浪況通知"],
]
for i, ((label, color), lines) in enumerate(zip(labels, items)):
    yy = y + i * (row_h + Inches(0.15))
    add_panel(slide, Inches(0.6), yy, Inches(12.1), row_h)
    lbox = slide.shapes.add_textbox(Inches(0.85), yy + Inches(0.08), Inches(2.6), row_h - Inches(0.16))
    tf = lbox.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]; r = p.add_run(); r.text = label
    set_font(r, size=17, color=color, bold=True)
    add_bullets(slide, lines, Inches(3.4), yy, Inches(9.1), row_h, size=14)

# =========================================================
# SLIDE 18｜結語
# =========================================================
slide = add_slide()
y = add_title(slide, "從想法到上線的完整旅程", tag="結語")
add_panel(slide, Inches(0.6), y, Inches(12.1), Inches(4.0))
add_bullets(slide, [
    "這個專案學到的核心能力：",
    ("系統設計 — 多服務協作（Render + GitHub Actions + Supabase + LINE + Streamlit）", 1),
    ("API 整合 — 處理真實外部 API 的各種異常（SSL、過期、回傳 None 字串）", 1),
    ("資料工程 — 資料新鮮度、備援策略、容錯機制", 1),
    ("非同步處理 — Webhook 非同步化、背景執行緒", 1),
    ("衝浪科學 — 湧浪物理、GoOcean 分級、陸風判斷", 1),
], Inches(0.6), y, Inches(12.1), Inches(4.0), size=18)

quote_box = slide.shapes.add_textbox(Inches(0.6), y + Inches(4.15), Inches(12.1), Inches(0.6))
tf = quote_box.text_frame
p = tf.paragraphs[0]
r = p.add_run(); r.text = "「不只是會寫程式，而是用程式解決真實問題。」"
set_font(r, size=22, color=CORAL, bold=True, italic=True)

foot_box = slide.shapes.add_textbox(Inches(0.6), y + Inches(4.9), Inches(12.1), Inches(0.6))
tf = foot_box.text_frame
p = tf.paragraphs[0]
r = p.add_run(); r.text = "掃 QR Code 試用機器人 →　GitHub：https://github.com/BboyMelon/surf-robot"
set_font(r, size=16, color=WHITE)

OUT = "/Users/melon/Downloads/melon-agent/surf_robot/浪況機器人_專題簡報.pptx"
prs.save(OUT)
print(f"已產生：{OUT}（共 {len(prs.slides.__iter__().__length_hint__()) if False else len(prs.slides._sldIdLst)} 張投影片）")
