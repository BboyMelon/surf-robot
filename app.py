"""
前端訂閱網頁 — Streamlit
左欄：Email + LINE ID 訂閱表單 / 管理員後台
右欄：Windy 浪高地圖（台灣）
"""
import streamlit as st
import pandas as pd
from db import add_member, get_all_members, get_all_groups, get_all_profiles
from broadcast import remind_incomplete_profiles
from config import ADMIN_PASSWORD

st.set_page_config(
    page_title="🌊 浪況訂閱機器人",
    page_icon="🏄",
    layout="wide",
)

# ── 側邊欄：管理員專區 ────────────────────────────────────
with st.sidebar:
    st.title("🔐 管理員專區")
    pwd = st.text_input("管理員密碼", type="password")

    if pwd == ADMIN_PASSWORD:
        st.success("✅ 已驗證")

        st.subheader("個人訂閱名單")
        members = get_all_members()
        if members:
            df_m = pd.DataFrame(members)
            show_cols = [c for c in ["email", "line_id", "status", "created_at"] if c in df_m.columns]
            st.dataframe(df_m[show_cols], use_container_width=True)
        else:
            st.info("尚無訂閱者")

        st.subheader("群組訂閱名單")
        groups = get_all_groups()
        if groups:
            df_g = pd.DataFrame(groups)
            show_cols_g = [c for c in ["group_id", "status", "joined_at"] if c in df_g.columns]
            st.dataframe(df_g[show_cols_g], use_container_width=True)
        else:
            st.info("尚無群組")

        st.subheader("🏄 Surfer 檔案")
        profiles = get_all_profiles()
        if profiles:
            df_p = pd.DataFrame(profiles)
            show_cols_p = [c for c in ["display_name", "gender", "surf_years", "board_type", "fav_spots", "updated_at"] if c in df_p.columns]
            st.dataframe(df_p[show_cols_p], use_container_width=True)
        else:
            st.info("尚無用戶檔案")

        st.divider()
        st.subheader("📣 推播管理")
        if st.button("⚠️ 提醒未填資料的用戶", use_container_width=True):
            with st.spinner("推播中..."):
                result = remind_incomplete_profiles()
            if result["total"] == 0:
                st.success("✅ 所有訂閱者都已填寫完整資料！")
            else:
                st.success(f"✅ 已推播 {result['ok']} 人 / 失敗 {result['fail']} 人（共 {result['total']} 位未填完）")

        if st.button("🔄 重新整理"):
            st.rerun()

    elif pwd:
        st.error("密碼錯誤")

# ── 主頁面：左右分欄 ──────────────────────────────────────
st.title("🌊 浪況訂閱機器人")
st.markdown("訂閱後每日清晨 05:00 收到台灣三大浪點浪況早報！")
st.divider()

col_left, col_right = st.columns([1, 1.6])

# 左欄：訂閱表單
with col_left:
    st.subheader("📋 加入訂閱")
    with st.form("subscribe_form"):
        email  = st.text_input("Email", placeholder="your@email.com")
        line_id = st.text_input(
            "LINE User ID",
            placeholder="Uxxxxxxxxxxx",
            help="在 LINE 開發者後台或浪況機器人回覆『我的ID』取得"
        )
        submitted = st.form_submit_button("🏄 立即訂閱", use_container_width=True)

    if submitted:
        if not email or not line_id:
            st.warning("請填寫 Email 與 LINE ID")
        elif not line_id.startswith("U"):
            st.warning("LINE User ID 通常以大寫 U 開頭，請確認")
        else:
            ok, msg = add_member(email.strip(), line_id.strip())
            if ok:
                st.success(f"✅ {msg} 明天早上見！")
                st.balloons()
            else:
                st.error(f"❌ 寫入失敗：{msg}")

    st.divider()
    st.subheader("📡 三大監測浪點")
    spots = {
        "🌊 宜蘭外澳":    "陸風：西／西南／南",
        "🌊 金山沙珠灣":  "陸風：南／西南",
        "🌊 恆春佳樂水":  "陸風：西／西北",
    }
    for name, wind in spots.items():
        st.markdown(f"**{name}**  \n`{wind}`")

    st.divider()
    st.caption("資料來源：中央氣象署 + GoOcean 國家海洋研究院")

# 右欄：Windy 浪高地圖
with col_right:
    st.subheader("🗺️ 即時浪高地圖")
    windy_embed = """
    <iframe
        src="https://embed.windy.com/embed2.html?lat=23.8&lon=121.8&detailLat=24.5&detailLon=121.9&width=100%&height=480&zoom=7&level=surface&overlay=waves&product=ecmwf&menu=&message=true&marker=true&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=km%2Fh&metricTemp=%C2%B0C&radarRange=-1"
        width="100%"
        height="480"
        frameborder="0"
        style="border-radius:12px;"
    ></iframe>
    """
    st.components.v1.html(windy_embed, height=490)
    st.caption("資料模型：ECMWF | 圖層：Waves | 更新頻率：6小時")
