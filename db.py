"""
資料庫抽象層：自動偵測 Supabase 或降版使用本地 SQLite。
有設定 SUPABASE_URL + SUPABASE_KEY → 用雲端；否則用 surf_bot.db。
"""
import sqlite3
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
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            email      TEXT,
            line_id    TEXT UNIQUE,
            status     TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
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
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            line_id    TEXT UNIQUE,
            gender     TEXT,
            surf_years INTEGER DEFAULT 0,
            board_type TEXT,
            fav_spots  TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

if not USE_SUPABASE:
    init_sqlite()

# ── 個人訂閱 ──────────────────────────────────────────────────
def add_member(email: str, line_id: str) -> Tuple[bool, str]:
    try:
        if USE_SUPABASE:
            _sb.table("members").upsert(
                {"email": email, "line_id": line_id, "status": "active"},
                on_conflict="line_id"
            ).execute()
        else:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.execute(
                "INSERT OR REPLACE INTO members (email, line_id, status) VALUES (?,?,?)",
                (email, line_id, "active")
            )
            conn.commit()
            conn.close()
        return True, "訂閱成功！"
    except Exception as e:
        return False, str(e)

def get_all_members() -> List[dict]:
    if USE_SUPABASE:
        res = _sb.table("members").select("*").eq("status", "active").execute()
        return res.data
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM members WHERE status='active'").fetchall()
    conn.close()
    return [dict(r) for r in rows]

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
def save_profile(line_id: str, profile: dict) -> Tuple[bool, str]:
    """新增或更新使用者衝浪檔案。"""
    try:
        data = {
            "line_id":    line_id,
            "gender":     profile.get("gender", ""),
            "surf_years": profile.get("surf_years", 0),
            "board_type": profile.get("board_type", ""),
            "fav_spots":  profile.get("fav_spots", ""),
        }
        if USE_SUPABASE:
            _sb.table("profiles").upsert(data, on_conflict="line_id").execute()
        else:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.execute(
                """INSERT OR REPLACE INTO profiles
                   (line_id, gender, surf_years, board_type, fav_spots)
                   VALUES (?,?,?,?,?)""",
                (line_id, data["gender"], data["surf_years"],
                 data["board_type"], data["fav_spots"])
            )
            conn.commit()
            conn.close()
        return True, "Profile 已儲存"
    except Exception as e:
        return False, str(e)

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
