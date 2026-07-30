"""
資料庫抽象層：自動偵測 Supabase 或降版使用本地 SQLite。
有設定 SUPABASE_URL + SUPABASE_KEY → 用雲端；否則用 surf_bot.db。
"""
import sqlite3
from datetime import datetime, timezone
from typing import Tuple, List, Optional
from config import SUPABASE_URL, SUPABASE_KEY

USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)

if USE_SUPABASE:
    from supabase import create_client
    _sb = create_client(SUPABASE_URL, SUPABASE_KEY)

SQLITE_PATH = "surf_bot.db"

# ── SQLite 初始化 ─────────────────────────────────────────────
def init_sqlite():
    conn = sqlite3.connect(SQLITE_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS members (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            email           TEXT,
            line_id         TEXT UNIQUE,
            status          TEXT DEFAULT 'active',
            form_completed  BOOLEAN DEFAULT 0,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        c.execute("ALTER TABLE members ADD COLUMN form_completed BOOLEAN DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # 舊版資料庫已有此欄位
    c.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id  TEXT UNIQUE,
            status    TEXT DEFAULT 'active',
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            line_id      TEXT UNIQUE,
            nickname     TEXT,
            gender       TEXT,
            surf_years   INTEGER DEFAULT 0,
            board_type   TEXT,
            fav_spots    TEXT,
            display_name TEXT,
            updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        c.execute("ALTER TABLE profiles ADD COLUMN nickname TEXT")
    except sqlite3.OperationalError:
        pass  # 舊版資料庫已有此欄位
    c.execute("""
        CREATE TABLE IF NOT EXISTS alerts_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type TEXT NOT NULL,
            alert_key  TEXT NOT NULL,
            alerted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_alerts_log_type_key
        ON alerts_log (alert_type, alert_key)
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS contact_messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT,
            email      TEXT,
            message    TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

if not USE_SUPABASE:
    init_sqlite()

# ── 個人訂閱 ──────────────────────────────────────────────────
def add_member(email: str, line_id: str, form_completed: bool = False) -> Tuple[bool, str]:
    """
    新增/更新訂閱者。form_completed 預設 False（例如單純加好友觸發的 follow 事件）；
    Streamlit 訂閱表單送出成功時應傳入 form_completed=True，代表正式完成會員註冊，
    05:00 每日廣播只會推播給 form_completed=True 的會員。
    """
    try:
        if USE_SUPABASE:
            payload = {"email": email, "line_id": line_id, "status": "active"}
            if form_completed:
                # 只在 True 時才寫入該欄位，避免加好友事件（預設 False）
                # 在已完成表單的會員身上，把 form_completed 又覆寫回 False
                payload["form_completed"] = True
            _sb.table("members").upsert(payload, on_conflict="line_id").execute()
        else:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.execute(
                "INSERT OR REPLACE INTO members (email, line_id, status, form_completed) VALUES (?,?,?,?)",
                (email, line_id, "active", form_completed)
            )
            conn.commit()
            conn.close()
        return True, "訂閱成功！"
    except Exception as e:
        return False, str(e)

def set_form_completed(line_id: str, completed: bool = True) -> Tuple[bool, str]:
    """手動標記某會員是否完成註冊表單（影響是否收到 05:00 每日廣播）。"""
    try:
        if USE_SUPABASE:
            _sb.table("members").update({"form_completed": completed}).eq("line_id", line_id).execute()
        else:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.execute("UPDATE members SET form_completed=? WHERE line_id=?", (completed, line_id))
            conn.commit()
            conn.close()
        return True, "已更新"
    except Exception as e:
        return False, str(e)

def remove_member(line_id: str) -> None:
    try:
        if USE_SUPABASE:
            _sb.table("members").update({"status": "inactive"}).eq("line_id", line_id).execute()
        else:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.execute("UPDATE members SET status='inactive' WHERE line_id=?", (line_id,))
            conn.commit()
            conn.close()
    except Exception as e:
        print(f"[remove_member 失敗] {e}")

def get_all_members() -> List[dict]:
    if USE_SUPABASE:
        res = _sb.table("members").select("*").eq("status", "active").execute()
        return res.data
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM members WHERE status='active'").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_broadcast_members() -> List[dict]:
    """05:00 每日廣播的收件名單：active 且 form_completed=True（正式完成註冊的會員）。"""
    if USE_SUPABASE:
        res = _sb.table("members").select("*").eq("status", "active").eq("form_completed", True).execute()
        return res.data
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM members WHERE status='active' AND form_completed=1").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_member_status(line_id: str) -> Optional[str]:
    """回傳個人訂閱狀態（'active'/'paused'/'inactive'），找不到回傳 None。"""
    try:
        if USE_SUPABASE:
            res = _sb.table("members").select("status").eq("line_id", line_id).execute()
            return res.data[0]["status"] if res.data else None
        conn = sqlite3.connect(SQLITE_PATH)
        row = conn.execute("SELECT status FROM members WHERE line_id=?", (line_id,)).fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None

def pause_member(line_id: str) -> Tuple[bool, str]:
    """暫停個人推播（status='paused'，保留記錄）。"""
    try:
        if USE_SUPABASE:
            _sb.table("members").update({"status": "paused"}).eq("line_id", line_id).execute()
        else:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.execute("UPDATE members SET status='paused' WHERE line_id=?", (line_id,))
            conn.commit()
            conn.close()
        return True, "已暫停"
    except Exception as e:
        return False, str(e)

def resume_member(line_id: str) -> Tuple[bool, str]:
    """恢復個人推播（status='active'）。"""
    try:
        if USE_SUPABASE:
            _sb.table("members").update({"status": "active"}).eq("line_id", line_id).execute()
        else:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.execute("UPDATE members SET status='active' WHERE line_id=?", (line_id,))
            conn.commit()
            conn.close()
        return True, "已恢復"
    except Exception as e:
        return False, str(e)

# ── 群組訂閱 ──────────────────────────────────────────────────
def add_group(group_id: str) -> Tuple[bool, str]:
    try:
        if USE_SUPABASE:
            _sb.table("groups").upsert(
                {"group_id": group_id, "status": "active"},
                on_conflict="group_id"
            ).execute()
        else:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.execute(
                "INSERT OR REPLACE INTO groups (group_id, status) VALUES (?,?)",
                (group_id, "active")
            )
            conn.commit()
            conn.close()
        return True, "群組已加入！"
    except Exception as e:
        return False, str(e)

def remove_group(group_id: str) -> None:
    try:
        if USE_SUPABASE:
            _sb.table("groups").update({"status": "inactive"}).eq("group_id", group_id).execute()
        else:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.execute("UPDATE groups SET status='inactive' WHERE group_id=?", (group_id,))
            conn.commit()
            conn.close()
    except Exception as e:
        print(f"[remove_group 失敗] {e}")

def get_all_groups() -> List[dict]:
    if USE_SUPABASE:
        res = _sb.table("groups").select("*").eq("status", "active").execute()
        return res.data
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM groups WHERE status='active'").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── 使用者 Profile ────────────────────────────────────────────
PROFILE_FIELDS = ("nickname", "gender", "surf_years", "board_type", "fav_spots", "display_name")

def save_profile(line_id: str, profile: dict) -> Tuple[bool, str]:
    """
    新增或更新使用者衝浪檔案。
    line_id 為唯一鍵，同一 LINE 使用者永遠只會對應一筆檔案（upsert）。
    只會寫入 profile 裡實際有的欄位，不會把沒傳入的欄位覆蓋成空值。
    """
    data = {"line_id": line_id}
    data.update({k: profile[k] for k in PROFILE_FIELDS if k in profile})

    try:
        if USE_SUPABASE:
            _sb.table("profiles").upsert(data, on_conflict="line_id").execute()
        else:
            conn = sqlite3.connect(SQLITE_PATH)
            exists = conn.execute(
                "SELECT 1 FROM profiles WHERE line_id=?", (line_id,)
            ).fetchone()
            if exists:
                updates = {k: v for k, v in data.items() if k != "line_id"}
                set_clause = ", ".join(f"{k}=?" for k in updates)
                conn.execute(
                    f"UPDATE profiles SET {set_clause} WHERE line_id=?",
                    list(updates.values()) + [line_id]
                )
            else:
                cols = ", ".join(data.keys())
                placeholders = ", ".join("?" for _ in data)
                conn.execute(
                    f"INSERT INTO profiles ({cols}) VALUES ({placeholders})",
                    list(data.values())
                )
            conn.commit()
            conn.close()
        return True, "Profile 已儲存"
    except Exception as e:
        return False, str(e)


def update_display_name(line_id: str, display_name: str):
    """任何互動時更新 LINE 顯示名稱（upsert 只寫 display_name）。"""
    try:
        if USE_SUPABASE:
            _sb.table("profiles").upsert(
                {"line_id": line_id, "display_name": display_name},
                on_conflict="line_id"
            ).execute()
        else:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.execute(
                """INSERT INTO profiles (line_id, display_name)
                   VALUES (?,?)
                   ON CONFLICT(line_id) DO UPDATE SET display_name=excluded.display_name""",
                (line_id, display_name)
            )
            conn.commit()
            conn.close()
    except Exception:
        pass

def get_profile(line_id: str) -> Optional[dict]:
    """取得單一使用者的 Profile，找不到回傳 None。"""
    try:
        if USE_SUPABASE:
            res = _sb.table("profiles").select("*").eq("line_id", line_id).execute()
            return res.data[0] if res.data else None
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM profiles WHERE line_id=?", (line_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        return None

def get_all_profiles() -> List[dict]:
    """取得所有 Profile（廣播用）。"""
    try:
        if USE_SUPABASE:
            res = _sb.table("profiles").select("*").execute()
            return res.data
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM profiles").fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []

# ── 警戒 de-dup log ────────────────────────────────────────────
def log_alert(alert_type: str, alert_key: str) -> None:
    """記錄一筆警戒推播（swell/typhoon + 識別 key），供跨重啟的 de-dup 使用。"""
    try:
        if USE_SUPABASE:
            _sb.table("alerts_log").insert({"alert_type": alert_type, "alert_key": alert_key}).execute()
        else:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.execute(
                "INSERT INTO alerts_log (alert_type, alert_key) VALUES (?, ?)",
                (alert_type, alert_key)
            )
            conn.commit()
            conn.close()
    except Exception as e:
        print(f"[log_alert 失敗] {e}")


def get_last_alert_time(alert_type: str, alert_key: str) -> Optional[datetime]:
    """回傳最近一次警戒推播時間（timezone-aware），查無記錄回傳 None。"""
    try:
        if USE_SUPABASE:
            res = (
                _sb.table("alerts_log")
                .select("alerted_at")
                .eq("alert_type", alert_type)
                .eq("alert_key", alert_key)
                .order("alerted_at", desc=True)
                .limit(1)
                .execute()
            )
            if not res.data:
                return None
            dt = datetime.fromisoformat(res.data[0]["alerted_at"])
        else:
            conn = sqlite3.connect(SQLITE_PATH)
            row = conn.execute(
                "SELECT alerted_at FROM alerts_log WHERE alert_type=? AND alert_key=? ORDER BY alerted_at DESC LIMIT 1",
                (alert_type, alert_key)
            ).fetchone()
            conn.close()
            if not row:
                return None
            dt = datetime.fromisoformat(row[0])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception as e:
        print(f"[get_last_alert_time 失敗] {e}")
        return None


# ── tidelog-site 聯絡表單 ──────────────────────────────────────
def save_contact_message(name: str, email: str, message: str) -> Tuple[bool, str]:
    """存一筆 tidelog-site 聯絡表單訊息，供 Streamlit 後台／TablePlus 查看。"""
    try:
        if USE_SUPABASE:
            _sb.table("contact_messages").insert(
                {"name": name, "email": email, "message": message}
            ).execute()
        else:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.execute(
                "INSERT INTO contact_messages (name, email, message) VALUES (?, ?, ?)",
                (name, email, message)
            )
            conn.commit()
            conn.close()
        return True, "送出成功"
    except Exception as e:
        return False, str(e)


def get_all_contact_messages() -> List[dict]:
    """取得所有聯絡表單訊息（Streamlit 後台用），依時間新到舊排序。"""
    try:
        if USE_SUPABASE:
            res = _sb.table("contact_messages").select("*").order("created_at", desc=True).execute()
            return res.data
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM contact_messages ORDER BY created_at DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def has_alert_logged(alert_type: str, alert_key: str) -> bool:
    """颱風 de-dup：查詢某颱風 ID 是否曾推播過（跨 Render 重啟也有效）。
    查詢失敗時回傳 False（保守處理：允許推播，不重複壓制）。"""
    try:
        if USE_SUPABASE:
            res = (
                _sb.table("alerts_log")
                .select("id")
                .eq("alert_type", alert_type)
                .eq("alert_key", alert_key)
                .limit(1)
                .execute()
            )
            return bool(res.data)
        conn = sqlite3.connect(SQLITE_PATH)
        row = conn.execute(
            "SELECT 1 FROM alerts_log WHERE alert_type=? AND alert_key=?",
            (alert_type, alert_key)
        ).fetchone()
        conn.close()
        return row is not None
    except Exception as e:
        print(f"[has_alert_logged 失敗] {e}")
        return False
