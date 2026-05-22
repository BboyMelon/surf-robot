"""
每日定時廣播 — broadcast.py
資料來源：CWA O-B0075-001（主要），Open-Meteo Marine（fallback）
流程：抓浮標 API → Swell Eye 能量分析 → 比對陸風 → LINE Push 廣播
執行方式：
  - 立即測試：python broadcast.py --now
  - 排程常駐：python broadcast.py
  - crontab：  0 6 * * * python /path/to/broadcast.py --now
"""
import sys
import requests
import schedule
import time
from datetime import datetime
from typing import List
from config import LINE_CHANNEL_ACCESS_TOKEN, SURF_SPOTS_CONFIG, get_surf_level
from db import get_all_members, get_all_groups, get_all_profiles, get_profile

CWA_API_KEY = "CWA-548E18F6-09C1-4F44-A924-9E18773BFF4D"
CWA_MARINE_URL = (
    "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-B0075-001"
    f"?Authorization={CWA_API_KEY}&format=JSON"
)

# ── 浪點 → 最近浮標站對應表（CWA O-B0075-001）──────────────
SPOT_STATION_MAP = {
    # 北部
    "金山沙珠灣": "46778A",   # 北部外海浮標
    "翡翠灣":     "C6AH2",    # 東北角外海浮標（萬里/翡翠灣附近）
    # 宜蘭
    "宜蘭外澳":   "46757B",   # 東北角外海浮標
    "烏石港":     "46757B",   # 外澳/烏石港共用同一浮標（相鄰）
    # 中部
    "台中松柏港": "46714D",   # 台灣海峽中部浮標
    "外埔":       "COMC08",   # 台灣海峽中部浮標（外埔附近）
    # 東部（花蓮）
    "花蓮北濱公園": "46706A",  # 花蓮外海浮標（東部海域）
    "花蓮環保公園": "46706A",  # 同浮標，北濱/環保公園相鄰
    # 東部（台東）
    "台東金樽":     "46761F",  # 成功浮標（台東東河/金樽附近）
    "台東東河":     "46761F",  # 同浮標，金樽/東河相鄰
    # 南部
    "台南漁光島": "46699A",   # 西南部外海浮標（台南/高雄海域）
    "恆春南灣":   "46694A",   # 南部外海浮標（墾丁南灣）
    "恆春九鵬":   "C6S94",    # 恆春半島東側外海浮標
    "恆春佳樂水": "46694A",   # 南部外海浮標（墾丁佳樂水）
}

# 英文風向縮寫 → 中文對照
WIND_DIR_MAP = {
    "N": "北", "NNE": "北北東", "NE": "東北", "ENE": "東北東",
    "E": "東", "ESE": "東南東", "SE": "東南", "SSE": "南南東",
    "S": "南", "SSW": "南南西", "SW": "西南", "WSW": "西南西",
    "W": "西", "WNW": "西北西", "NW": "西北", "NNW": "北北西",
}

# ── 浮標站 GPS 座標（供 Open-Meteo fallback 使用）──────────
STATION_COORDS = {
    "46778A": (25.30, 121.70),  # 北部外海（金山附近）
    "C6AH2":  (25.10, 122.00),  # 東北角外海（翡翠灣）
    "46757B": (24.90, 122.00),  # 宜蘭外海（外澳/烏石港）
    "46714D": (24.20, 120.30),  # 台灣海峽中部（松柏港）
    "COMC08": (24.40, 120.50),  # 台灣海峽中部（外埔）
    "46706A": (24.00, 121.80),  # 花蓮外海
    "46761F": (23.10, 121.50),  # 台東/成功外海（金樽/東河）
    "46699A": (22.60, 120.20),  # 西南外海（台南漁光島）
    "46694A": (21.90, 120.90),  # 南部外海（墾丁南灣/佳樂水）
    "C6S94":  (22.10, 121.20),  # 恆春半島東側（九鵬）
}


def degrees_to_compass(deg: float) -> str:
    """角度（0-360）轉羅盤方向縮寫。"""
    dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
            "S","SSW","SW","WSW","W","WNW","NW","NNW"]
    return dirs[round(deg / 22.5) % 16]


# ── 步驟 A：抓取 CWA 浮標觀測資料 ───────────────────────
def fetch_marine_data() -> dict:
    """
    回傳格式：
    {
      "46761F": {
          "wave_height": 1.5,  # 單位 m
          "wave_period": 7.0,  # 單位 s
          "wave_dir": "E",
          "wind_speed": 3.2,   # 單位 m/s
          "wind_dir": "NE",
          "tide_height": 0.3,
          "tide_level": "漲潮",
          "sea_temp": 27.2,
          "datetime": "2026-05-20T09:00:00+08:00"
      }, ...
    }
    """
    result = {}
    try:
        resp = requests.get(CWA_MARINE_URL, timeout=15)
        resp.raise_for_status()
        d = resp.json()

        locations = d["Records"]["SeaSurfaceObs"]["Location"]

        for loc in locations:
            sid = loc["Station"]["StationID"]
            times = loc["StationObsTimes"]["StationObsTime"]
            if not times:
                continue

            latest = times[-1]
            we = latest.get("WeatherElements", {})
            anemo = we.get("PrimaryAnemometer", {})
            if not isinstance(anemo, dict):
                anemo = {}

            def safe_float(val, default=0.0):
                try:
                    return float(val)
                except (TypeError, ValueError):
                    return default

            result[sid] = {
                "wave_height": safe_float(we.get("WaveHeight")),
                "wave_period": safe_float(we.get("WavePeriod")),
                "wave_dir":    we.get("WaveDirectionDescription", ""),
                "wind_speed":  safe_float(anemo.get("WindSpeed")),
                "wind_dir":    anemo.get("WindDirectionDescription", ""),
                "tide_height": safe_float(we.get("TideHeight")),
                "tide_level":  we.get("TideLevel", ""),
                "sea_temp":    safe_float(we.get("SeaTemperature")),
                "datetime":    latest.get("DateTime", ""),
            }

    except Exception as e:
        print(f"[CWA API 錯誤] {e}")

    return result


# ── 步驟 A2：Open-Meteo Marine API（Render 可存取的 fallback）──
def fetch_marine_data_openmeteo() -> dict:
    """
    使用 Open-Meteo Marine API 取得波浪/風況資料。
    免費、無 API Key、全球 IP 均可存取。
    海溫/潮位無法取得，以 None 回傳（顯示時會改為「—」）。
    """
    result = {}
    try:
        station_ids = list(STATION_COORDS.keys())
        lats = ",".join(str(STATION_COORDS[s][0]) for s in station_ids)
        lons = ",".join(str(STATION_COORDS[s][1]) for s in station_ids)

        # 波浪資料（Open-Meteo Marine API）
        marine_resp = requests.get(
            "https://marine-api.open-meteo.com/v1/marine",
            params={
                "latitude": lats,
                "longitude": lons,
                "current": "wave_height,wave_period,wave_direction",
                "timezone": "Asia/Taipei",
            },
            timeout=15,
        )
        marine_resp.raise_for_status()
        marine_data = marine_resp.json()

        # 風況資料（Open-Meteo Weather API）
        wind_resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lats,
                "longitude": lons,
                "current": "wind_speed_10m,wind_direction_10m",
                "timezone": "Asia/Taipei",
            },
            timeout=15,
        )
        wind_resp.raise_for_status()
        wind_data = wind_resp.json()

        # 多地點回傳 list，單一地點回傳 dict，統一轉成 list
        marine_list = marine_data if isinstance(marine_data, list) else [marine_data]
        wind_list   = wind_data   if isinstance(wind_data,   list) else [wind_data]

        now_str = datetime.now().strftime("%Y-%m-%dT%H:%M")

        for i, sid in enumerate(station_ids):
            mc = marine_list[i].get("current", {}) if i < len(marine_list) else {}
            wc = wind_list[i].get("current", {})   if i < len(wind_list)   else {}

            wave_dir_deg = float(mc.get("wave_direction") or 0.0)
            wind_dir_deg = float(wc.get("wind_direction_10m") or 0.0)

            result[sid] = {
                "wave_height": float(mc.get("wave_height")    or 0.0),
                "wave_period": float(mc.get("wave_period")    or 0.0),
                "wave_dir":    degrees_to_compass(wave_dir_deg),
                "wind_speed":  float(wc.get("wind_speed_10m") or 0.0),
                "wind_dir":    degrees_to_compass(wind_dir_deg),
                "tide_height": None,   # Open-Meteo 不提供潮位
                "tide_level":  "—",
                "sea_temp":    None,   # Open-Meteo 不提供海溫
                "datetime":    now_str,
            }

        result["_meta"] = {"source": "open-meteo"}
        print(f"[Open-Meteo] 成功取得 {len(station_ids)} 個浮標站資料")

    except Exception as e:
        print(f"[Open-Meteo API 錯誤] {e}")

    return result


# ── 資料取得入口（CWA 優先，失敗改用 Open-Meteo）────────────
def get_marine_data() -> dict:
    """優先用 CWA 浮標資料；Render 環境被封鎖時自動切換 Open-Meteo。"""
    data = fetch_marine_data()
    if not data:
        print("[資料切換] CWA 無回應，改用 Open-Meteo Marine API")
        data = fetch_marine_data_openmeteo()
    return data


# ── Swell Eye：湧浪能量 ───────────────────────────────────
def swell_energy(wave_height: float, period: float) -> float:
    """湧浪能量 = 浪高(m) × 週期(s)"""
    return round(wave_height * period, 2)


# ── 陸風判斷 ─────────────────────────────────────────────
def is_offshore(wind_dir_en: str, offshore_list: List[str]) -> bool:
    zh = WIND_DIR_MAP.get(wind_dir_en.upper(), "")
    return any(o in zh for o in offshore_list)

# ── 個人化評分 ────────────────────────────────────────────
def personal_rating(wave_h: float, period: float, profile: dict) -> str:
    """
    依使用者浪齡、板型給出個人化建議語句。
    """
    years      = profile.get("surf_years", 0) if profile else 0
    board_type = (profile.get("board_type", "") or "") if profile else ""

    # 技術等級分類
    if years <= 1:
        skill = "beginner"
    elif years <= 4:
        skill = "intermediate"
    else:
        skill = "advanced"

    # 板型提示
    board_warn = ""
    if "短" in board_type and period < 7:
        board_warn = "\n🛹 浪力偏弱，短板可能滑不太起來"
    elif "長" in board_type and wave_h > 1.8:
        board_warn = "\n🛹 浪況偏大，長板入水請謹慎"

    # 技術等級對應評語
    if skill == "beginner":
        if wave_h > 1.2:
            rating = "⚠️ 超出新手安全範圍，今天建議先在岸上觀察"
        elif wave_h >= 0.3:
            rating = "✅ 適合新手練習！今天可以下水衝！"
        else:
            rating = "😴 浪太小，練習划水的好機會"
    elif skill == "intermediate":
        if wave_h > 2.5:
            rating = "⚠️ 浪況偏大，請謹慎評估後再入水"
        elif wave_h >= 0.8:
            rating = "🤙 不錯的浪！適合你的程度，衝吧！"
        else:
            rating = "😊 浪小，可以練習動作技巧"
    else:  # advanced
        if wave_h >= 1.5 and period >= 8:
            rating = "🔥 衝浪黃金期！今天是好浪，快出發！"
        elif wave_h >= 1.0:
            rating = "👍 浪況不錯，值得出發"
        else:
            rating = "😑 浪況偏弱，短板可能沒力，長板還行"

    return rating + board_warn


# ── 組裝每日浪況簡報 ──────────────────────────────────────
def build_report(marine: dict) -> str:
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    source = marine.get("_meta", {}).get("source", "cwa")
    lines = [f"🌊 每日浪況早報\n📅 {today}\n"]

    current_category = ""
    for spot_name, spot_cfg in SURF_SPOTS_CONFIG.items():
        # 地區分隔標題
        cat = spot_cfg.get("category", "")
        if cat != current_category:
            current_category = cat
            lines.append(f"{'═'*16}\n{cat}\n{'═'*16}")

        station_id = SPOT_STATION_MAP.get(spot_name)
        data       = marine.get(station_id, {})

        wave_h   = data.get("wave_height", 0.0)
        period   = data.get("wave_period", 0.0)
        wave_dir = data.get("wave_dir", "—")
        wind_dir = data.get("wind_dir", "—")
        wind_spd = data.get("wind_speed", 0.0)
        tide_h   = data.get("tide_height")   # 可能為 None（Open-Meteo）
        tide_lv  = data.get("tide_level", "—")
        sea_t    = data.get("sea_temp")      # 可能為 None（Open-Meteo）
        obs_dt   = data.get("datetime", "")[:16].replace("T", " ")

        sea_t_str = f"{sea_t:.1f}°C" if sea_t is not None else "—"
        tide_str  = f"{tide_h:.2f}m（{tide_lv}）" if tide_h is not None else "—"

        energy       = swell_energy(wave_h, period)
        level        = get_surf_level(wave_h, period)
        offshore     = is_offshore(wind_dir, spot_cfg["offshore_wind"])
        offshore_tag = "✅ 黃金陸風" if offshore else "❌ 向岸風"
        swell_warn   = " ⚠️ 長浪警戒！" if (period > 8 and wave_h > 1.5) else ""

        if wave_h == 0.0 and period == 0.0:
            lines.append(
                f"📍 {spot_name}\n"
                f"━━━━━━━━━━━━\n"
                f"📡 站碼：{station_id}\n"
                f"⚠️ 暫無即時觀測資料\n"
            )
            continue

        lines.append(
            f"📍 {spot_name}\n"
            f"━━━━━━━━━━━━\n"
            f"🌊 浪高：{wave_h:.1f}m{swell_warn}\n"
            f"⏱ 週期：{period:.1f}s\n"
            f"🧭 浪向：{wave_dir}\n"
            f"💨 風向：{wind_dir} {wind_spd:.1f}m/s {offshore_tag}\n"
            f"🌡 水溫：{sea_t_str}\n"
            f"🕐 潮位：{tide_str}\n"
            f"⚡ 湧浪能量：{energy}\n"
            f"🏄 分級：{level['label']}\n"
            f"⚠️ {spot_cfg['safety_note']}\n"
            f"🕒 觀測時間：{obs_dt}\n"
        )

    lines.append("─────────────────")
    if source == "open-meteo":
        lines.append("📡 資料：Open-Meteo Marine（模型預報）")
        lines.append("⚠️ 潮位/水溫暫不顯示（海外伺服器備援模式）")
    else:
        lines.append("📡 資料：中央氣象署 O-B0075-001")
    lines.append("🗺️ 地圖：goocean.namr.gov.tw")

    return "\n".join(lines)


# ── LINE Push 廣播 ────────────────────────────────────────
def push_line_message(to: str, text: str) -> bool:
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"to": to, "messages": [{"type": "text", "text": text}]}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"  [Push 失敗] to={to[:10]}... err={e}")
        return False


# ── 主廣播任務 ────────────────────────────────────────────
def build_personal_report(marine: dict, profile: dict) -> str:
    """為有 Profile 的使用者產生個人化簡報（只顯示常衝浪點）。"""
    today    = datetime.now().strftime("%Y-%m-%d %H:%M")
    years    = profile.get("surf_years", 0)
    board    = profile.get("board_type", "")
    fav_raw  = profile.get("fav_spots", "") or ""

    # 技術等級標籤
    if years <= 1:
        skill_tag = "🌱 新手"
    elif years <= 4:
        skill_tag = "🏄 中級"
    else:
        skill_tag = "🔥 進階"

    # 找出使用者常去的浪點（模糊比對 config 浪點名稱）
    fav_list = [s.strip() for s in fav_raw.replace("、", ",").replace("，", ",").split(",") if s.strip()]
    matched_spots = []
    for spot in SURF_SPOTS_CONFIG:
        if any(fav in spot or spot in fav for fav in fav_list):
            matched_spots.append(spot)
    # 若沒匹配到，顯示全部
    target_spots = matched_spots if matched_spots else list(SURF_SPOTS_CONFIG.keys())

    lines = [
        f"🌊 專屬浪況早報｜{skill_tag}",
        f"📅 {today}",
        f"🛹 板型：{board or '未設定'} | 浪齡：{years} 年",
        "",
    ]

    current_cat = ""
    for spot_name in target_spots:
        spot_cfg   = SURF_SPOTS_CONFIG[spot_name]
        station_id = SPOT_STATION_MAP.get(spot_name)
        data       = marine.get(station_id, {})

        cat = spot_cfg.get("category", "")
        if cat != current_cat:
            current_cat = cat
            lines.append(f"{'═'*16}\n{cat}\n{'═'*16}")

        wave_h   = data.get("wave_height", 0.0)
        period   = data.get("wave_period", 0.0)
        wave_dir = data.get("wave_dir", "—")
        wind_dir = data.get("wind_dir", "—")
        wind_spd = data.get("wind_speed", 0.0)
        obs_dt   = data.get("datetime", "")[:16].replace("T", " ")

        offshore     = is_offshore(wind_dir, spot_cfg["offshore_wind"])
        offshore_tag = "✅ 陸風" if offshore else "❌ 向岸"
        swell_warn   = " ⚠️ 長浪警戒！" if (period > 8 and wave_h > 1.5) else ""
        p_rating     = personal_rating(wave_h, period, profile)

        if wave_h == 0.0 and period == 0.0:
            lines.append(f"📍 {spot_name}\n⚠️ 暫無觀測資料\n")
            continue

        lines.append(
            f"📍 {spot_name}\n"
            f"🌊 {wave_h:.1f}m{swell_warn} ⏱{period:.1f}s 🧭{wave_dir}\n"
            f"💨 {wind_dir} {wind_spd:.1f}m/s {offshore_tag}\n"
            f"👤 {p_rating}\n"
            f"⚠️ {spot_cfg['safety_note']}\n"
        )

    lines.append("─────────────────")
    lines.append("📡 中央氣象署 O-B0075-001")
    return "\n".join(lines)


def broadcast():
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🌊 開始廣播...")

    marine = get_marine_data()
    if not marine:
        print("  ⚠️ 無法取得浮標資料（CWA + Open-Meteo 均失敗），廣播取消")
        return

    # 通用簡報（給群組 / 無 profile 的人）
    generic_report = build_report(marine)

    print("── 通用簡報預覽 ──────────────")
    print(generic_report)
    print("──────────────────────────────")

    members  = get_all_members()
    groups   = get_all_groups()
    ok, fail = 0, 0

    # 個人：依 profile 個人化
    for m in members:
        lid = m.get("line_id", "")
        if not lid or not lid.startswith("U"):
            continue
        profile = get_profile(lid)
        if profile and profile.get("surf_years") is not None:
            msg = build_personal_report(marine, profile)
        else:
            msg = generic_report
        if push_line_message(lid, msg):
            ok += 1
        else:
            fail += 1

    # 群組：統一通用版
    for g in groups:
        gid = g.get("group_id", "")
        if gid:
            if push_line_message(gid, generic_report):
                ok += 1
            else:
                fail += 1

    total = len(members) + len(groups)
    print(f"  ✅ 廣播完成：{ok} 成功 / {fail} 失敗 / {total} 總計")


# ── 執行入口 ─────────────────────────────────────────────
if __name__ == "__main__":
    if "--now" in sys.argv:
        broadcast()
    else:
        print("🌊 浪況廣播排程啟動，每日 05:00 發送...")
        print("   立即測試請用：python broadcast.py --now")
        schedule.every().day.at("05:00").do(broadcast)
        while True:
            schedule.run_pending()
            time.sleep(30)
