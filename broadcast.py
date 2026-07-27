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
import math
import json as _json
import subprocess
import requests
import schedule
import time
from datetime import datetime, timedelta, timezone

TW_TZ = timezone(timedelta(hours=8))  # 台灣時間 UTC+8
from typing import List
from config import SURF_SPOTS_CONFIG, CWA_API_KEY, ADMIN_LINE_ID, get_surf_level
from db import get_all_members, get_broadcast_members, get_all_groups, get_all_profiles, log_alert, get_last_alert_time, has_alert_logged
from line_api import push_text as push_line_message

# CWA 開放資料平台的證書鏈缺少 Subject Key Identifier 欄位。Render 上的 Python
# ssl 模組（OpenSSL 3.2+）在憑證鏈解析階段就直接拒絕連線，不管 verify=False
# 還是自訂 SSLContext 清除嚴格旗標都沒用（已實測兩者皆失敗）——這個檢查發生在
# Python ssl 模組底層，比任何 requests/urllib3 層級的設定都早。改用 curl
# 子行程（-k 跳過憑證驗證），curl 走自己的 TLS 驗證邏輯，不會踩到同一個問題。
# CWA 是公開氣象資料，沒有敏感資料外洩風險。
def _cwa_get(url: str, params: dict = None, timeout: int = 10, retries: int = 3) -> dict:
    if params:
        from urllib.parse import urlencode
        url = f"{url}?{urlencode(params)}"
    last_err = ""
    for attempt in range(1, retries + 1):
        result = subprocess.run(
            ["curl", "-sk", "--max-time", str(timeout), url],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        if result.returncode == 0:
            return _json.loads(result.stdout)
        last_err = f"curl 失敗（code {result.returncode}）：{result.stderr.strip()}"
        if attempt < retries:
            print(f"  [_cwa_get] 第 {attempt} 次失敗，2 秒後重試...")
            time.sleep(2)
    raise RuntimeError(last_err)


CWA_MARINE_URL = (
    "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-B0075-001"
    f"?Authorization={CWA_API_KEY}&format=JSON"
)
CWA_TIDE_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-A0021-001"

# ── 浪點 → 最近浮標站對應表（CWA O-B0075-001）──────────────
SPOT_STATION_MAP = {
    # 北部
    "金山沙珠灣": "46778A",   # 北部外海浮標
    "翡翠灣":     "C6AH2",    # 東北角外海浮標
    "中角灣":     "46778A",   # 北部外海浮標（石門/金山海域）
    "烏石港":     "46757B",   # 東北角外海浮標
    # 宜蘭
    "宜蘭外澳":   "46757B",   # 東北角外海浮標
    # 中部
    "松柏港福德里": "46714D",  # 台灣海峽中部浮標
    "外埔漁港":     "COMC08",  # 台灣海峽中部浮標（外埔附近）
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
    "46778A": (25.30, 121.70),  # 北部外海（金山/中角灣）
    "C6AH2":  (25.10, 122.00),  # 東北角外海（翡翠灣）
    "46757B": (24.90, 122.00),  # 東北角外海（烏石港/外澳）
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


# 浮標資料新鮮度門檻（小時）。颱風期間浮標常斷線，CWA 仍會持續回傳斷線前
# 的最後一筆紀錄而不會報錯，必須自己檢查時間，否則會把颱風來之前的「平靜」
# 假象當成即時浪況繼續推薦。
MARINE_DATA_MAX_AGE_HOURS = 3


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
        d = _cwa_get(CWA_MARINE_URL, timeout=8)

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

            def safe_str(val) -> str:
                # CWA API 有時回傳字串 "None" 而非 Python None
                return "—" if not val or str(val).strip() in ("None", "null", "") else str(val)

            # 新鮮度檢查：時間格式異常時不擋資料（避免誤殺），只擋確認過期的
            obs_time_str = latest.get("DateTime", "")
            age_hours = 0.0
            try:
                obs_time = datetime.fromisoformat(obs_time_str)
                age_hours = (datetime.now(TW_TZ) - obs_time).total_seconds() / 3600
            except (ValueError, TypeError):
                pass

            # 浪高/週期感測器若沒有實際回傳數值，CWA 會給字串 "None"；這跟
            # 「真的測到 0」是完全不同的意思，不能套用 safe_float 的 0.0 預設值
            raw_wave_height = we.get("WaveHeight")
            raw_wave_period = we.get("WavePeriod")
            wave_sensor_down = (
                str(raw_wave_height).strip() in ("None", "null", "")
                or str(raw_wave_period).strip() in ("None", "null", "")
            )

            if age_hours > MARINE_DATA_MAX_AGE_HOURS or wave_sensor_down:
                if sid in STATION_COORDS:  # 只記錄我們實際監測的浪點站，避免洗版
                    print(f"  ⚠️ 站號 {sid} 資料異常（過期 {age_hours:.1f} 小時，"
                          f"浪高感測器離線={wave_sensor_down}），略過此站")
                continue

            result[sid] = {
                "wave_height": safe_float(raw_wave_height),
                "wave_period": safe_float(raw_wave_period),
                "wave_dir":    safe_str(we.get("WaveDirectionDescription")),
                "wind_speed":  safe_float(anemo.get("WindSpeed")),
                "wind_dir":    safe_str(anemo.get("WindDirectionDescription")),
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
            timeout=20,
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
            timeout=20,
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


# ── 步驟 A3：Open-Meteo Marine 明日預報（hourly）───────────
def fetch_tomorrow_forecast() -> dict:
    """
    取得明日浪況預報，使用 Open-Meteo Marine hourly API。
    取明日 06:00-18:00 的平均波高/週期/方向。
    回傳格式：{station_id: {wave_height, wave_period, wave_dir}}
    """
    tomorrow = (datetime.now(TW_TZ) + timedelta(days=1)).strftime("%Y-%m-%d")
    station_ids = list(STATION_COORDS.keys())
    lats = ",".join(str(STATION_COORDS[s][0]) for s in station_ids)
    lons = ",".join(str(STATION_COORDS[s][1]) for s in station_ids)

    result = {}
    try:
        resp = requests.get(
            "https://marine-api.open-meteo.com/v1/marine",
            params={
                "latitude":   lats,
                "longitude":  lons,
                "hourly":     "wave_height,wave_period,wave_direction",
                "timezone":   "Asia/Taipei",
                "start_date": tomorrow,
                "end_date":   tomorrow,
            },
            timeout=8,
        )
        resp.raise_for_status()
        raw       = resp.json()
        data_list = raw if isinstance(raw, list) else [raw]

        for i, sid in enumerate(station_ids):
            if i >= len(data_list):
                break
            hourly     = data_list[i].get("hourly", {})
            times      = hourly.get("time", [])
            heights    = hourly.get("wave_height", [])
            periods    = hourly.get("wave_period", [])
            directions = hourly.get("wave_direction", [])

            h_vals, p_vals, d_vals = [], [], []
            for j, t in enumerate(times):
                hour = int(t[11:13])
                if 6 <= hour <= 18:
                    if j < len(heights)    and heights[j]    is not None:
                        h_vals.append(float(heights[j]))
                    if j < len(periods)    and periods[j]    is not None:
                        p_vals.append(float(periods[j]))
                    if j < len(directions) and directions[j] is not None:
                        d_vals.append(float(directions[j]))

            if h_vals:
                result[sid] = {
                    "wave_height": round(sum(h_vals) / len(h_vals), 1),
                    "wave_period": round(sum(p_vals) / len(p_vals), 1) if p_vals else 0.0,
                    "wave_dir":    degrees_to_compass(sum(d_vals) / len(d_vals)) if d_vals else "—",
                }

        print(f"[明日預報] 成功取得 {len(result)} 個站點資料")
    except Exception as e:
        print(f"[明日預報 API 錯誤] {e}")

    return result


# ── 步驟 A4：CWA 潮汐預報（F-A0021-001，今日滿潮/乾潮時刻）──────
def fetch_tide_today(location_id: str) -> dict:
    """
    取得指定潮汐站「今天」的潮汐時刻表。
    回傳格式：{"tide_range": "小"/"中"/"大", "events": [{"time": "03:30", "type": "乾潮", "height_cm": "25"}, ...]}
    查無資料（站點錯誤或當天無預報）則回傳空 dict。
    """
    today = datetime.now(TW_TZ).strftime("%Y-%m-%d")
    try:
        data = _cwa_get(
            CWA_TIDE_URL,
            params={"Authorization": CWA_API_KEY, "format": "JSON", "LocationId": location_id},
            timeout=8,
        )
        forecasts = data["records"]["TideForecasts"]
        if not forecasts:
            return {}

        daily = forecasts[0]["Location"]["TimePeriods"]["Daily"]
        today_entry = next((day for day in daily if day["Date"] == today), None)
        if not today_entry:
            return {}

        events = sorted(today_entry["Time"], key=lambda t: t["DateTime"])
        return {
            "tide_range": today_entry.get("TideRange", "—"),
            "events": [
                {
                    "time":      ev["DateTime"][11:16],
                    "type":      ev["Tide"],
                    "height_cm": ev["TideHeights"].get("AboveTWVD", "—"),
                }
                for ev in events
            ],
        }
    except Exception as e:
        print(f"[潮汐 API 錯誤] {e}")
        return {}


def build_tide_line(tide: dict) -> str:
    """將潮汐時刻表格式化為文字（含下一次滿/乾潮提示）。查無資料回傳空字串。"""
    events = tide.get("events") if tide else None
    if not events:
        return ""

    now_hm = datetime.now(TW_TZ).strftime("%H:%M")
    lines  = [f"🌙 潮汐（{tide['tide_range']}潮）"]
    for i in range(0, len(events), 2):
        pair = events[i:i + 2]
        lines.append("｜".join(f"{ev['type']} {ev['time']}" for ev in pair))

    next_ev = next((ev for ev in events if ev["time"] > now_hm), None)
    if next_ev:
        lines.append(f"⏰ 下次{next_ev['type']} {next_ev['time']}")
    return "\n".join(lines)


# ── 資料取得入口（CWA 優先，缺失站用 Open-Meteo 補充）──────
def get_marine_data() -> dict:
    """
    優先用 CWA 浮標資料。
    - CWA 完全空白 → 全切 Open-Meteo（retry 2 次）
    - CWA 部分缺站 → 用 Open-Meteo 補充缺失的站，避免顯示「暫無觀測資料」
    """
    cwa_data = fetch_marine_data()

    if not cwa_data:
        # CWA 全部無效（全過期 or API 錯誤）→ 完整切換 Open-Meteo
        print("[資料切換] CWA 全部無效，改用 Open-Meteo Marine API")
        for attempt in range(1, 4):
            om = fetch_marine_data_openmeteo()
            if om:
                return om
            print(f"[Open-Meteo] 第 {attempt} 次重試失敗，5 秒後再試一次...")
            time.sleep(5)
        return {}

    missing = set(STATION_COORDS.keys()) - set(cwa_data.keys())
    if missing:
        # CWA 部分站缺失 → 從 Open-Meteo 補充，避免浪點顯示「暫無觀測資料」
        print(f"[資料補充] CWA 缺少 {len(missing)} 站，向 Open-Meteo 補充：{', '.join(sorted(missing))}")
        om = fetch_marine_data_openmeteo()
        for sid in missing:
            if sid in om:
                cwa_data[sid] = om[sid]

    return cwa_data


# ── Swell Eye：湧浪能量 ───────────────────────────────────
def swell_energy(wave_height: float, period: float) -> float:
    """湧浪能量 = 浪高(m) × 週期(s)（原始值，用於顯示）"""
    return round(wave_height * period, 2)


def period_quality_factor(period: float) -> float:
    """
    週期品質加權係數。
    短週期風浪（Wind swell）雜亂打板，長週期湧浪（Ground swell）乾淨有力，
    相同浪高下品質差距極大。
      < 7s  → 0.7  （短週期風浪，雜亂）
      7-9s  → 1.0  （一般）
      9-12s → 1.3  （長週期混合浪）
     ≥ 12s  → 1.6  （Ground swell，最佳品質）
    """
    if period >= 12:
        return 1.6
    if period >= 9:
        return 1.3
    if period >= 7:
        return 1.0
    return 0.7


def swell_quality_score(wave_h: float, period: float) -> float:
    """排序/星數用品質分數 = 能量 × 週期品質係數"""
    return swell_energy(wave_h, period) * period_quality_factor(period)


# ── 陸風判斷 ─────────────────────────────────────────────
def is_offshore(wind_dir_en: str, offshore_list: List[str]) -> bool:
    zh = WIND_DIR_MAP.get(wind_dir_en.upper(), "")
    return any(o in zh for o in offshore_list)


def ms_to_beaufort(ms: float) -> int:
    """m/s 轉蒲福風級。"""
    thresholds = [0.3, 1.6, 3.4, 5.5, 8.0, 10.8, 13.9, 17.2, 20.8, 24.5, 28.5, 32.7]
    for scale, t in enumerate(thresholds):
        if ms < t:
            return scale
    return 12


def surf_stars(wave_h: float, period: float, offshore: bool) -> str:
    """依品質分數（能量×週期係數）+ 陸風回傳星數字串（1–5 顆）。"""
    level = get_surf_level(wave_h, period)
    if level["emoji"] == "⛔":
        return "🚫"
    score = swell_quality_score(wave_h, period)
    if score < 3:
        stars = 1
    elif score < 5:
        stars = 2
    elif score < 10:
        stars = 3
    elif score < 18:
        stars = 4
    else:
        stars = 5
    if offshore:
        stars = min(5, stars + 1)
    return "⭐" * stars


def spot_summary_line(wave_h: float, period: float, level: dict) -> str:
    """推薦浪人描述行（等級名稱 + 一行評語）。"""
    emoji = level["emoji"]
    if emoji == "⛔":
        return "👤 推薦浪人：危險封閉，請勿入水"
    if emoji == "🟢":
        desc = "浪況平穩，適合初學者練習" if wave_h >= 0.3 else "浪非常小，練習划水的好機會"
        zh = "初學"
    elif emoji == "🟡":
        desc = "浪小，可以練習動作技巧" if wave_h < 0.8 else "浪況適中，盡情享受！"
        zh = "中階"
    else:
        desc = "長浪爆發！衝浪黃金期" if (wave_h >= 1.5 and period >= 8) else "浪大刺激，建議有豐富經驗者"
        zh = "進階"
    return f"👤 推薦浪人：{zh}，{desc}"


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


# ── 今日最佳浪點 ─────────────────────────────────────────
def find_best_spots(marine: dict, top_n: int = 3) -> list:
    """
    依湧浪能量 + 陸風加成，找出今日最佳浪點。
    跳過無資料及危險封閉浪點，不額外消耗 API 呼叫。
    """
    seen_stations: set = set()  # 同浮標站只取第一個浪點，避免重複上榜
    scored = []
    for spot_name, spot_cfg in SURF_SPOTS_CONFIG.items():
        sid  = SPOT_STATION_MAP.get(spot_name)
        if not sid or sid in seen_stations:
            continue
        data = marine.get(sid, {})
        wave_h   = data.get("wave_height", 0.0)
        period   = data.get("wave_period", 0.0)
        wind_dir = data.get("wind_dir") or "—"

        if wave_h == 0.0 and period == 0.0:
            continue

        level = get_surf_level(wave_h, period)
        if level["emoji"] == "⛔":
            continue

        seen_stations.add(sid)
        offshore = is_offshore(wind_dir, spot_cfg["offshore_wind"])
        energy   = swell_energy(wave_h, period)
        score    = swell_quality_score(wave_h, period) * (1.3 if offshore else 1.0)

        scored.append({
            "name":     spot_name,
            "wave_h":   wave_h,
            "period":   period,
            "wind_dir": wind_dir,
            "stars":    surf_stars(wave_h, period, offshore),
            "level":    level,
            "score":    score,
            "offshore": offshore,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]


def build_best_spot_section(marine: dict) -> str:
    """生成「今日最佳浪點」推薦區塊，嵌入廣播開頭。"""
    best = find_best_spots(marine)
    if not best:
        return ""

    medals = ["🥇", "🥈", "🥉"]
    lines  = ["🏆 今日最佳浪點推薦"]
    for i, b in enumerate(best):
        medal   = medals[i] if i < 3 else "  "
        of_tag  = "｜🌬️ 陸風" if b["offshore"] else ""
        lines.append(
            f"{medal} {b['name']}  {b['stars']} {b['level']['emoji']}\n"
            f"   🌊 {b['wave_h']:.1f}m｜週期 {b['period']:.0f}s{of_tag}"
        )
    lines.append("──────────────────")
    return "\n".join(lines)


# ── 全台總覽（每區一行精簡摘要）────────────────────────────
def build_overview_report(marine: dict) -> str:
    """
    打「總覽」回傳：每個地區各一行，顯示代表浮標的浪況摘要。
    每個 category 取第一個有資料的浪點作代表。
    """
    now_str = datetime.now(TW_TZ).strftime("%m/%d %H:%M")
    lines   = [f"🗺️ 全台浪況總覽｜{now_str}", ""]

    seen_cats: dict = {}
    for spot_name, spot_cfg in SURF_SPOTS_CONFIG.items():
        cat = spot_cfg.get("category", "")
        if cat in seen_cats:
            continue
        sid  = SPOT_STATION_MAP.get(spot_name)
        data = marine.get(sid, {}) if sid else {}
        wave_h = data.get("wave_height", 0.0)
        period = data.get("wave_period", 0.0)
        if wave_h == 0.0 and period == 0.0:
            continue
        wind_dir = data.get("wind_dir") or "—"
        offshore = is_offshore(wind_dir, spot_cfg["offshore_wind"])
        level    = get_surf_level(wave_h, period)
        stars    = surf_stars(wave_h, period, offshore)
        of_tag   = " 🌬️" if offshore else ""
        seen_cats[cat] = True
        lines.append(f"{cat}  {wave_h:.1f}m · {period:.0f}s{of_tag}  {stars} {level['emoji']}")

    source = marine.get("_meta", {}).get("source", "cwa")
    lines += [
        "",
        "📡 " + ("Open-Meteo Marine（備援）" if source == "open-meteo" else "中央氣象署 O-B0075-001"),
        "💡 輸入地區名稱查詳細浪況（例：北部、花蓮）",
    ]
    return "\n".join(lines)


# ── 單一浪點格式化（共用於廣播/個人化/即時查詢三處）──────────
def build_spot_block(spot_name: str, cfg: dict, data: dict,
                      profile: dict = None, tide_line: str = "") -> list:
    """回傳單一浪點的文字行清單。tide_line 由呼叫端自己抓好再傳入，
    這個函式只負責格式化，不處理潮汐 API 呼叫。"""
    wave_h   = data.get("wave_height", 0.0)
    period   = data.get("wave_period", 0.0)
    wind_dir = data.get("wind_dir") or "—"
    wind_spd = data.get("wind_speed", 0.0)

    if wave_h == 0.0 and period == 0.0:
        return [f"📍 {spot_name}", "⚠️ 暫無觀測資料"]

    offshore   = is_offshore(wind_dir, cfg.get("offshore_wind", []))
    wind_dir_zh = WIND_DIR_MAP.get(wind_dir.upper(), wind_dir)
    level      = get_surf_level(wave_h, period)
    swell_warn = " ⚠️長浪！" if (period > 8 and wave_h > 1.5) else ""
    stars      = surf_stars(wave_h, period, offshore)
    bft        = ms_to_beaufort(wind_spd)
    summary    = spot_summary_line(wave_h, period, level)

    lines = [
        f"📍 {spot_name}{swell_warn}",
        f"🌊 浪高：{wave_h:.1f}   週期：{period:.0f}",
        f"💨 風力平均：{bft}級  風向：{wind_dir_zh}",
        f"🏄 浪況推薦：{stars} {level['emoji']}",
        summary,
    ]

    safety = cfg.get("safety_note", "")
    if safety:
        lines.append(f"⚠️ {safety}")

    if tide_line:
        lines.append(tide_line)

    if profile:
        lines.append(f"💬 {personal_rating(wave_h, period, profile)}")

    return lines


# ── 組裝每日浪況簡報 ──────────────────────────────────────
def build_report(marine: dict, tomorrow_forecast: dict = None) -> str:
    now_tw = datetime.now(TW_TZ)
    today  = now_tw.strftime("%Y-%m-%d %H:%M")
    session = "下午快報" if 12 <= now_tw.hour < 20 else "早報"
    source = marine.get("_meta", {}).get("source", "cwa")
    lines = [f"🌊 每日浪況{session}\n📅 {today}\n"]

    best_section = build_best_spot_section(marine)
    if best_section:
        lines.append(best_section)
        lines.append("")

    current_category = ""
    for spot_name, spot_cfg in SURF_SPOTS_CONFIG.items():
        # 地區分隔標題
        cat = spot_cfg.get("category", "")
        if cat != current_category:
            current_category = cat
            lines.append(f"\n── {cat} ──")

        station_id = SPOT_STATION_MAP.get(spot_name)
        data       = marine.get(station_id, {})
        lines.extend(build_spot_block(spot_name, spot_cfg, data))

    lines.append("")
    if source == "open-meteo":
        lines.append("📡 Open-Meteo Marine（備援模式）")
    else:
        lines.append("📡 中央氣象署 O-B0075-001")
    lines.append("🗺️ goocean.namr.gov.tw")
    lines.append("💡 輸入 help 查看指令總覽")

    # 附加明日概況
    if tomorrow_forecast:
        tomorrow_block = build_tomorrow_section(tomorrow_forecast)
        if tomorrow_block:
            lines.append(tomorrow_block)

    return "\n".join(lines)


# ── 明日預報：廣播用概覽（每區一行）────────────────────────
def build_tomorrow_section(forecast: dict) -> str:
    """生成廣播底部的明日概況區塊（每區取第一個有資料的代表站）。"""
    if not forecast:
        return ""

    tomorrow_date = (datetime.now(TW_TZ) + timedelta(days=1)).strftime("%m/%d")
    seen_cats: dict = {}
    for spot_name, spot_cfg in SURF_SPOTS_CONFIG.items():
        cat = spot_cfg.get("category", "")
        if cat in seen_cats:
            continue
        sid = SPOT_STATION_MAP.get(spot_name)
        if sid and sid in forecast:
            seen_cats[cat] = forecast[sid]

    if not seen_cats:
        return ""

    lines = [f"\n🌅 明日概況（{tomorrow_date} 白天均值）"]
    for cat, d in seen_cats.items():
        wh = d.get("wave_height", 0.0)
        wp = d.get("wave_period", 0.0)
        wd = d.get("wave_dir", "—")
        level    = get_surf_level(wh, wp)
        level_zh = level["label"].split()[1] if len(level["label"].split()) > 1 else level["label"]
        lines.append(f"{cat}：{wh:.1f}m·{wp:.0f}s·{wd}  {level['emoji']}{level_zh}")

    lines.append("（📡 Open-Meteo 預報模型）")
    return "\n".join(lines)


# ── 明日預報：完整版（查詢指令用）──────────────────────────
def build_tomorrow_full_report(forecast: dict) -> str:
    """明日浪況完整預報，格式與即時查詢相同。"""
    tomorrow_date = (datetime.now(TW_TZ) + timedelta(days=1)).strftime("%Y-%m-%d")
    lines = [
        f"🌅 明日浪況預報",
        f"📅 {tomorrow_date}（06:00–18:00 均值）",
        "",
    ]

    current_cat = ""
    for spot_name, spot_cfg in SURF_SPOTS_CONFIG.items():
        cat = spot_cfg.get("category", "")
        if cat != current_cat:
            current_cat = cat
            lines.append(f"\n── {cat} ──")

        sid = SPOT_STATION_MAP.get(spot_name)
        d   = forecast.get(sid, {}) if sid else {}

        if not d:
            lines.append(f"📍 {spot_name}")
            lines.append("⚠️ 暫無預報資料")
            continue

        wh = d.get("wave_height", 0.0)
        wp = d.get("wave_period", 0.0)
        wd = d.get("wave_dir", "—")
        wd_zh = WIND_DIR_MAP.get(wd.upper(), wd)
        level      = get_surf_level(wh, wp)
        swell_warn = " ⚠️長浪！" if (wp > 8 and wh > 1.5) else ""
        stars      = surf_stars(wh, wp, False)  # 預報無風向資料，陸風不計入
        summary    = spot_summary_line(wh, wp, level)

        lines.append(f"📍 {spot_name}{swell_warn}")
        lines.append(f"🌊 浪高：{wh:.1f}   週期：{wp:.0f}   浪向：{wd_zh}")
        lines.append(f"🏄 浪況推薦：{stars} {level['emoji']}")
        lines.append(summary)

    lines.append("")
    lines.append("📡 Open-Meteo Marine 7天預報模型")
    lines.append("（實際浪況仍以當日即時資料為準）")
    return "\n".join(lines)


# ── 主廣播任務 ────────────────────────────────────────────
def build_personal_report(marine: dict, profile: dict) -> str:
    """為有 Profile 的使用者產生個人化簡報（只顯示常衝浪點）。"""
    now_tw   = datetime.now(TW_TZ)
    today    = now_tw.strftime("%Y-%m-%d %H:%M")
    session  = "下午快報" if 12 <= now_tw.hour < 20 else "早報"
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
        f"🌊 專屬浪況{session}｜{skill_tag}",
        f"📅 {today}",
        f"🛹 板型：{board or '未設定'} | 浪齡：{years} 年",
        "",
    ]

    best_section = build_best_spot_section(marine)
    if best_section:
        lines.append(best_section)
        lines.append("")

    current_cat = ""
    for spot_name in target_spots:
        spot_cfg   = SURF_SPOTS_CONFIG[spot_name]
        station_id = SPOT_STATION_MAP.get(spot_name)
        data       = marine.get(station_id, {})

        cat = spot_cfg.get("category", "")
        if cat != current_cat:
            current_cat = cat
            lines.append(f"\n── {cat} ──")

        lines.extend(build_spot_block(spot_name, spot_cfg, data, profile=profile))

    source = marine.get("_meta", {}).get("source", "cwa")
    lines.append("")
    lines.append("📡 " + ("Open-Meteo Marine（備援模式）" if source == "open-meteo" else "中央氣象署 O-B0075-001"))
    lines.append("💡 輸入 help 查看指令總覽")
    return "\n".join(lines)


def broadcast():
    print(f"\n[{datetime.now(TW_TZ).strftime('%Y-%m-%d %H:%M:%S')} TW] 🌊 開始廣播...")

    marine = get_marine_data()
    if not marine:
        print("  ⚠️ 無法取得浮標資料（CWA + Open-Meteo 均失敗），廣播取消")
        push_line_message(ADMIN_LINE_ID, "⚠️ 今日浪況廣播取消：CWA + Open-Meteo 浮標資料皆取得失敗，請檢查兩個 API 狀態。")
        return

    # 取明日預報（失敗不中斷廣播）
    tomorrow_forecast = fetch_tomorrow_forecast()

    # 通用簡報（給群組 / 無 profile 的人）
    generic_report = build_report(marine, tomorrow_forecast)

    print("── 通用簡報預覽 ──────────────")
    print(generic_report)
    print("──────────────────────────────")

    members  = get_broadcast_members()  # 只推給完成註冊表單的會員，非全部 active 訂閱者
    groups   = get_all_groups()
    profiles = {p["line_id"]: p for p in get_all_profiles()}  # 一次批次查，避免每位訂閱者各打一次DB
    ok, fail = 0, 0

    # 個人：依 profile 個人化
    for m in members:
        lid = m.get("line_id", "")
        if not lid or not lid.startswith("U"):
            continue
        profile = profiles.get(lid)
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


# ── 未填資料提醒 ──────────────────────────────────────────
PROFILE_REMINDER = """👋 嗨！你還沒建立衝浪檔案喔～

填寫後可以解鎖：
✅ 每日專屬浪況早報（只顯示你常去的浪點）
✅ 根據浪齡給出個人化建議
✅ 板型適合度提示

請複製以下格式，填寫後直接回傳 👇

━━━━━━━━━━━━
性別：（男 / 女 / 其他）
浪齡：（例：3）
版型：（長板 / 短板 / 中長板）
常衝浪點：（填入你常去的浪點）
━━━━━━━━━━━━

填完後每日 05:00 就會收到專屬浪況早報 🌊"""


def remind_incomplete_profiles() -> dict:
    """
    找出所有尚未填寫完整 Profile 的訂閱者，推播填寫提醒。
    「未完整」= 沒有 profiles 記錄，或 gender/surf_years/board_type 任一為空。
    回傳推播結果統計。
    """
    members  = get_all_members()
    profiles = {p["line_id"]: p for p in get_all_profiles()}

    incomplete = []
    for m in members:
        lid = m.get("line_id", "")
        if not lid or not lid.startswith("U"):
            continue
        p = profiles.get(lid)
        if not p:
            incomplete.append(lid)
            continue
        # 任一必填欄位為空 → 視為未完整
        if not p.get("gender") or not p.get("board_type") or p.get("surf_years") is None:
            incomplete.append(lid)

    ok = fail = 0
    for lid in incomplete:
        if push_line_message(lid, PROFILE_REMINDER):
            ok += 1
        else:
            fail += 1

    print(f"[提醒] 未填資料用戶：{len(incomplete)} 人，推播 {ok} 成功 / {fail} 失敗")
    return {"total": len(incomplete), "ok": ok, "fail": fail}


# ── 警戒閾值設定 ─────────────────────────────────────────
SWELL_HEIGHT_THRESHOLD = 1.5   # m，超過才觸發
SWELL_PERIOD_THRESHOLD = 8.0   # s，超過才觸發
SWELL_ALERT_COOLDOWN   = 6     # 同一站至少間隔幾小時才再推

CWA_TYPHOON_URL = (
    "https://opendata.cwa.gov.tw/api/v1/rest/datastore/W-C0034-005"
    f"?Authorization={CWA_API_KEY}&format=JSON"
)

TAIWAN_LAT = 23.5   # 台灣中心座標
TAIWAN_LON = 121.0
TYPHOON_ALERT_KM = 1000  # 距離門檻（公里）


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """計算兩點球面距離（Haversine 公式，單位 km）。"""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return round(R * 2 * math.asin(math.sqrt(a)), 0)


def push_alert_to_all(msg: str):
    """推播警戒訊息給所有個人訂閱者 + 群組。"""
    ok = fail = 0
    for m in get_all_members():
        lid = m.get("line_id", "")
        if lid and lid.startswith("U"):
            if push_line_message(lid, msg):
                ok += 1
            else:
                fail += 1
    for g in get_all_groups():
        gid = g.get("group_id", "")
        if gid:
            if push_line_message(gid, msg):
                ok += 1
            else:
                fail += 1
    print(f"  [警戒推播] {ok} 成功 / {fail} 失敗")


def check_swell_alerts():
    """
    每 3 小時自動執行。波高 >= 1.5m 且週期 >= 8s → 立即推播長浪警戒。
    同一浮標站 6 小時內最多推一次（in-memory de-dup）。
    """
    now = datetime.now(TW_TZ)
    print(f"[{now.strftime('%Y-%m-%d %H:%M')}] 🔍 長浪警戒檢查中...")

    marine = get_marine_data()
    if not marine:
        print("  ⚠️ 無法取得浮標資料，跳過")
        return

    # 以浮標站為單位，收集超標浪點（de-dup 存 Supabase，Render 重啟後仍有效）
    triggered: dict = {}  # {station_id: [(spot_name, wh, wp), ...]}

    for spot_name, spot_cfg in SURF_SPOTS_CONFIG.items():
        sid  = SPOT_STATION_MAP.get(spot_name)
        data = marine.get(sid, {}) if sid else {}
        wh   = data.get("wave_height", 0.0)
        wp   = data.get("wave_period", 0.0)

        if wh >= SWELL_HEIGHT_THRESHOLD and wp >= SWELL_PERIOD_THRESHOLD:
            last = get_last_alert_time("swell", sid)
            if last is None or (now - last).total_seconds() > SWELL_ALERT_COOLDOWN * 3600:
                triggered.setdefault(sid, []).append((spot_name, wh, wp))

    if not triggered:
        print("  ✅ 各浪點均在安全範圍內")
        return

    for sid in triggered:
        log_alert("swell", sid)

    lines = [
        "🚨 長浪警戒通知 🚨",
        f"📅 {now.strftime('%Y-%m-%d %H:%M')}",
        "",
        "偵測到以下浪點出現危險長浪：",
        "",
    ]
    for sid, spots in triggered.items():
        for spot_name, wh, wp in spots:
            energy   = swell_energy(wh, wp)
            level    = get_surf_level(wh, wp)
            cfg      = SURF_SPOTS_CONFIG.get(spot_name, {})
            lines += [
                f"📍 {spot_name}",
                f"🌊 浪高：{wh:.1f}m ｜ 週期：{wp:.1f}s",
                f"⚡ 湧浪能量：{energy}",
                f"🏄 級別：{level['label']}",
                f"⚠️ {cfg.get('safety_note', '')}",
                "",
            ]
    lines += [
        "──────────────────",
        "⛔ 危險海況，強烈建議暫停入水",
        "📡 即時監測：浪況機器人自動偵測",
    ]

    print(f"  🚨 觸發長浪警戒：{list(triggered.keys())}")
    push_alert_to_all("\n".join(lines))


def check_typhoon_alerts():
    """
    每 1 小時自動執行。呼叫 CWA W-C0034-005，
    出現新熱帶氣旋（ID 未推播過）時立即通知所有訂閱者。
    Render 海外 IP 可能被封鎖，例外一律靜默忽略。
    """
    now = datetime.now(TW_TZ)
    print(f"[{now.strftime('%Y-%m-%d %H:%M')}] 🌀 颱風警報檢查中...")

    try:
        data = _cwa_get(CWA_TYPHOON_URL, timeout=10)

        # 實際 API 結構：records.TropicalCyclones.TropicalCyclone（陣列）
        records = data.get("records") or data.get("Records") or {}
        cyclones = records.get("TropicalCyclones", {}).get("TropicalCyclone") or []
        # 單筆時 API 可能回傳 dict 而非 list
        if isinstance(cyclones, dict):
            cyclones = [cyclones]

        if not cyclones:
            print("  ✅ 目前無活動熱帶氣旋")
            return

        for ty in cyclones:
            year        = ty.get("Year", "")
            ty_no       = ty.get("CwaTyNo") or ty.get("CwaTdNo", "")
            ty_id       = f"{year}-{ty_no}"
            ty_name     = ty.get("CwaTyphoonName", "未知")
            ty_name_eng = ty.get("TyphoonName", "")
            warn_level  = "颱風" if ty.get("CwaTyNo") else "熱帶性低氣壓"

            if not ty_id or has_alert_logged("typhoon", ty_id):
                continue

            # 取最新實況座標（AnalysisData.Fix 最後一筆）
            fixes = ty.get("AnalysisData", {}).get("Fix") or []
            if isinstance(fixes, dict):
                fixes = [fixes]
            latest = fixes[-1] if fixes else {}
            try:
                ty_lat = float(latest.get("CoordinateLatitude", 0))
                ty_lon = float(latest.get("CoordinateLongitude", 0))
                dist_km = haversine_km(TAIWAN_LAT, TAIWAN_LON, ty_lat, ty_lon)
            except (ValueError, TypeError):
                dist_km = 9999

            if dist_km > TYPHOON_ALERT_KM:
                print(f"  ℹ️ {ty_name}（{ty_id}）距台灣 {dist_km:.0f} km，超過 {TYPHOON_ALERT_KM} km 門檻，略過")
                continue

            log_alert("typhoon", ty_id)

            lines = [
                "🌀 熱帶氣旋通知 🌀",
                f"📅 {now.strftime('%Y-%m-%d %H:%M')}",
                "",
                f"⚠️ 中央氣象署偵測到活動中的{warn_level}！",
                "",
                f"🌀 名稱：{ty_name}（{ty_name_eng}）",
                f"🔴 類型：{warn_level}",
                f"📍 目前位置：{ty_lat:.1f}°N  {ty_lon:.1f}°E",
                f"📏 距台灣：約 {dist_km:.0f} km",
                "",
                "🏄 請密切注意氣象局最新公告",
                "📻 海況可能在未來數日快速惡化",
                "🏥 衝浪前務必確認最新警報狀態",
                "──────────────────",
                "📡 資料：中央氣象署 W-C0034-005",
            ]
            print(f"  🌀 偵測到{warn_level}：{ty_name}（{ty_id}）距台灣 {dist_km:.0f} km → 推播")
            push_alert_to_all("\n".join(lines))

    except Exception as e:
        print(f"  [颱風 API 錯誤] {e}")


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
