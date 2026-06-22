"""
Supabase → Google Sheet 資料同步
讀取 members / groups / profiles 三張表，整批覆寫進對應分頁，方便用 Google Sheet 檢視/篩選訂閱資料。
執行方式：
  - 本機測試：python3 sync_to_sheets.py
  - 排程：GitHub Actions sync_sheets.yml（每日跑一次，也可手動 workflow_dispatch 觸發）
"""
import os
import json
import gspread
from google.oauth2.service_account import Credentials
from db import get_all_members, get_all_groups, get_all_profiles

GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_sheet_client() -> gspread.Client:
    creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not creds_json:
        raise RuntimeError("缺少環境變數 GOOGLE_SERVICE_ACCOUNT_JSON（Google 服務帳號金鑰 JSON）")
    info  = json.loads(creds_json)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


def write_rows(spreadsheet: gspread.Spreadsheet, sheet_name: str, rows: list) -> None:
    """清空分頁後整批寫入。資料量小（數十~數百筆），整批覆寫比逐筆比對簡單可靠。"""
    try:
        ws = spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=sheet_name, rows=200, cols=12)

    ws.clear()
    if not rows:
        return

    headers = list(rows[0].keys())
    values  = [headers] + [[str(r.get(h, "")) for h in headers] for r in rows]
    ws.update(values)
    print(f"[{sheet_name}] 已寫入 {len(rows)} 筆")


def sync_all() -> None:
    if not GOOGLE_SHEET_ID:
        raise RuntimeError("缺少環境變數 GOOGLE_SHEET_ID（目標 Google Sheet 的 ID）")

    client      = get_sheet_client()
    spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)

    write_rows(spreadsheet, "members", get_all_members())
    write_rows(spreadsheet, "groups", get_all_groups())
    write_rows(spreadsheet, "profiles", get_all_profiles())

    print("[同步完成] ✅")


if __name__ == "__main__":
    sync_all()
