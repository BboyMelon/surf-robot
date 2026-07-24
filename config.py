import os
from dotenv import load_dotenv

load_dotenv()

# ── 金鑰環境變數 ──────────────────────────────────────────
CWA_API_KEY             = os.getenv("CWA_API_KEY", "")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET     = os.getenv("LINE_CHANNEL_SECRET", "")
SUPABASE_URL            = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY            = os.getenv("SUPABASE_KEY", "")

ADMIN_PASSWORD   = "surf123"
ADMIN_LINE_ID    = os.getenv("ADMIN_LINE_ID", "Ubbf53a642514770a3f153b40fcd34a4c")
BROADCAST_TOKEN  = os.getenv("BROADCAST_TOKEN", "surf-broadcast-2026")
STREAMLIT_URL    = os.getenv("STREAMLIT_URL", "（尚未部署，敬請期待 🚀）")

# ── 浪點設定：地區 / 陸風方向 / 安全提示 ─────────────────────
SURF_SPOTS_CONFIG = {
    # ── 北部 ──────────────────────────────────────────────────
    "金山沙珠灣": {
        "category":     "🔵 北部",
        "offshore_wind": ["南", "西南"],
        "safety_note":  "注意水母與左側礁石區",
    },
    "翡翠灣": {
        "category":     "🔵 北部",
        "offshore_wind": ["南", "東南"],
        "safety_note":  "私人海灣，西側礁岩勿靠近",
    },
    "中角灣": {
        "category":     "🔵 北部",
        "offshore_wind": ["南", "西南", "西"],
        "safety_note":  "礁岩地形，浪型多變，注意退流",
    },
    "烏石港": {
        "category":     "🔵 北部",
        "offshore_wind": ["西", "西南", "南"],
        "safety_note":  "防波堤北側礁岩區，注意退流",
    },
    "宜蘭外澳": {
        "category":     "🔵 北部",
        "offshore_wind": ["西", "西南", "南"],
        "safety_note":  "注意防波堤旁離岸流",
    },
    # ── 中部 ──────────────────────────────────────────────────
    "松柏港福德里": {
        "category":     "🟡 中部",
        "offshore_wind": ["東", "東南", "東北"],
        "safety_note":  "冬季東北季風浪較佳，注意強流",
    },
    "外埔漁港": {
        "category":     "🟡 中部",
        "offshore_wind": ["東", "東南"],
        "safety_note":  "沙灘型浪點，注意離岸流與砂泥底質",
    },
    # ── 東部 ────────────────────────────────────────────────────
    "花蓮北濱公園": {
        "category":     "🟠 東部",
        "offshore_wind": ["西", "西北", "西南"],
        "safety_note":  "礫石灘，退潮暗礁多，注意強離岸流",
    },
    "花蓮環保公園": {
        "category":     "🟠 東部",
        "offshore_wind": ["西", "西北", "西南"],
        "safety_note":  "礫石底質，浪崩快，注意下浪時機",
    },
    "台東金樽": {
        "category":     "🟠 東部",
        "offshore_wind": ["西", "西北", "西南"],
        "safety_note":  "礁岩型，退潮大石裸露，建議有經驗者入水",
    },
    "台東東河": {
        "category":     "🟠 東部",
        "offshore_wind": ["西", "西北", "西南"],
        "safety_note":  "沙礫混合底質，注意人潮與流向",
    },
    # ── 南部 ──────────────────────────────────────────────────
    "台南漁光島": {
        "category":     "🔴 南部",
        "offshore_wind": ["東", "東南", "東北"],
        "safety_note":  "沙灘型浪點，浪小適合長板，注意岸邊砂洲與潮汐變化",
    },
    "恆春南灣": {
        "category":     "🔴 南部｜恆春",
        "offshore_wind": ["北", "東北", "西北"],
        "safety_note":  "熱門觀光沙灘，人潮多，夏季水母頻繁，注意衝浪區域劃分",
    },
    "恆春九鵬": {
        "category":     "🔴 南部｜恆春",
        "offshore_wind": ["西", "西北", "西南"],
        "safety_note":  "半島東側礁岩地形，浪型多變，注意強流與離岸流",
    },
    "恆春佳樂水": {
        "category":     "🔴 南部｜恆春",
        "offshore_wind": ["西", "西北"],
        "safety_note":  "河口地形，退潮時注意暗礁",
    },
}

# ── 浪點 → 最近潮汐站對應表（CWA F-A0021-001，未來1個月潮汐預報）──
# 優先採用 CWA「衝浪」分類潮汐站；無對應衝浪站則採用最近的海水浴場/漁港/行政區站
TIDE_STATION_MAP = {
    "金山沙珠灣": "O00100",    # 衝浪中角沙珠灣
    "翡翠灣":     "A01500",    # 海水浴場翡翠灣
    "中角灣":     "O00100",    # 衝浪中角沙珠灣
    "烏石港":     "I00100",    # 漁港烏石
    "宜蘭外澳":   "I00100",    # 漁港烏石（外澳緊鄰烏石港）
    "松柏港福德里": "10009130", # 雲林縣麥寮鄉
    "外埔漁港":     "I04100",   # 漁港外埔
    "花蓮北濱公園": "10015010", # 花蓮縣花蓮市
    "花蓮環保公園": "10015010", # 花蓮縣花蓮市
    "台東金樽":     "O01300",   # 衝浪金樽
    "台東東河":     "10014070", # 臺東縣東河鄉
    "台南漁光島": "67000360",  # 臺南市安平區
    "恆春南灣":   "O00700",    # 衝浪南灣
    "恆春九鵬":   "10013240",  # 屏東縣滿州鄉
    "恆春佳樂水": "10013240",  # 屏東縣滿州鄉
}

# ── GoOcean 衝浪分級門檻（官方標準）────────────────────────
SURF_LEVEL = [
    {"label": "🟢 初學 Primary",    "max_height": 1.2, "max_period": 7,  "emoji": "🟢"},
    {"label": "🟡 中階 Intermediate","max_height": 2.5, "max_period": 9,  "emoji": "🟡"},
    {"label": "🔴 進階 Expert",      "max_height": 8.0, "max_period": 12, "emoji": "🔴"},
    {"label": "⛔ 危險封閉",          "max_height": 99,  "max_period": 99, "emoji": "⛔"},
]

def get_surf_level(wave_height: float, wave_period: float) -> dict:
    """
    依照 GoOcean 分級回傳等級結果。
    主要依浪高判斷，長週期湧浪（ground swell）另外調升一個等級：
      ⛔ 危險：浪高 ≥ 3m，或浪高 ≥ 2m 且週期 ≥ 12s（大浪強湧浪）
      🔴 進階：浪高 ≥ 1.8m，或浪高 ≥ 1.0m 且週期 ≥ 12s（中浪長湧浪，能量大）
      🟡 中階：浪高 ≥ 0.8m，或浪高 ≥ 0.5m 且週期 ≥ 9s
      🟢 初學：其餘
    """
    if wave_height >= 3.0 or (wave_height >= 2.0 and wave_period >= 12):
        return SURF_LEVEL[3]  # ⛔
    if wave_height >= 1.8 or (wave_height >= 1.0 and wave_period >= 12):
        return SURF_LEVEL[2]  # 🔴
    if wave_height >= 0.8 or (wave_height >= 0.5 and wave_period >= 9):
        return SURF_LEVEL[1]  # 🟡
    return SURF_LEVEL[0]     # 🟢
