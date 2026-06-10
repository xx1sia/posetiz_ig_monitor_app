import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from db import init_db
from collector import collect_once

DB_PATH = Path("data/instagram_monitor.db")

st.set_page_config(
    page_title="POSETIZ Instagram Monitor",
    page_icon="📈",
    layout="wide"
)
def check_password():
    if "APP_PASSWORD" not in st.secrets:
        return True

    if st.session_state.get("password_ok"):
        return True

    st.title("🔒 POSETIZ Instagram Monitor")
    st.caption("팀 내부용 대시보드입니다.")

    password = st.text_input("접속 비밀번호를 입력하세요", type="password")

    if st.button("접속하기"):
        if password == st.secrets["APP_PASSWORD"]:
            st.session_state["password_ok"] = True
            st.rerun()
        else:
            st.error("비밀번호가 맞지 않아.")

    return False


if not check_password():
    st.stop()
    
st.title("📈 POSETIZ Instagram Monitor")
st.caption("1시간 단위 인스타그램 성과 추적 대시보드")


def load_data():
    init_db()

    conn = sqlite3.connect(DB_PATH)

    media_df = pd.read_sql_query(
        "SELECT * FROM media_snapshots",
        conn
    )

    account_df = pd.read_sql_query(
        "SELECT * FROM account_snapshots",
        conn
    )

    conn.close()

    if not media_df.empty:
        media_df["collected_at"] = pd.to_datetime(media_df["collected_at"])
        media_df["hour"] = media_df["collected_at"].dt.strftime("%Y-%m-%d %H:00")

    if not account_df.empty:
        account_df["collected_at"] = pd.to_datetime(account_df["collected_at"])
        account_df["hour"] = account_df["collected_at"].dt.strftime("%Y-%m-%d %H:00")

    return media_df, account_df


def calculate_hourly_delta(media_df):
    if media_df.empty:
        return pd.DataFrame()

    sort_cols = ["media_id", "collected_at"]
    df = media_df.sort_values(sort_cols).copy()

    metrics = ["like_count", "comments_count", "views", "saved", "shares"]

    for metric in metrics:
        df[f"{metric}_delta"] = df.groupby("media_id")[metric].diff().fillna(0)

    return df


col1, col2 = st.columns([1, 3])

with col1:
    if st.button("지금 한 번 수집하기"):
        with st.spinner("인스타그램 데이터를 수집 중..."):
            result = collect_once(limit=25)

        st.success(
            f"수집 완료: {result['collected_at']} / "
            f"미디어 {result['media_count']}개 / "
            f"팔로워 {result['followers_count']:,}명"
        )

media_df, account_df = load_data()
delta_df = calculate_hourly_delta(media_df)

if media_df.empty:
    st.warning("아직 수집된 데이터가 없어. 먼저 '지금 한 번 수집하기'를 눌러.")
    st.stop()

latest_time = media_df["collected_at"].max()
latest_df = media_df[media_df["collected_at"] == latest_time]

st.subheader("현재 최신 수집 기준")

total_likes = latest_df["like_count"].sum()
total_comments = latest_df["comments_count"].sum()
total_views = latest_df["views"].sum()
total_saved = latest_df["saved"].sum()
total_shares = latest_df["shares"].sum()

m1, m2, m3, m4, m5 = st.columns(5)

m1.metric("좋아요 합계", f"{total_likes:,}")
m2.metric("댓글 합계", f"{total_comments:,}")
m3.metric("조회수 합계", f"{total_views:,}")
m4.metric("저장수 합계", f"{total_saved:,}")
m5.metric("공유수 합계", f"{total_shares:,}")

st.divider()

st.subheader("1시간 단위 증가량")

if delta_df.empty:
    st.info("증가량을 보려면 최소 2번 이상 수집되어야 해.")
else:
    hourly = delta_df.groupby("hour", as_index=False)[
        [
            "like_count_delta",
            "comments_count_delta",
            "views_delta",
            "saved_delta",
            "shares_delta"
        ]
    ].sum()

    fig = px.line(
        hourly,
        x="hour",
        y=[
            "like_count_delta",
            "comments_count_delta",
            "views_delta",
            "saved_delta",
            "shares_delta"
        ],
        markers=True,
        title="시간대별 성과 증가량"
    )

    st.plotly_chart(fig, use_container_width=True)

st.divider()

st.subheader("급상승 콘텐츠 TOP 10")

if not delta_df.empty:
    latest_delta_time = delta_df["collected_at"].max()
    latest_delta = delta_df[delta_df["collected_at"] == latest_delta_time].copy()

    latest_delta["score"] = (
        latest_delta["views_delta"] * 0.3
        + latest_delta["like_count_delta"] * 1
        + latest_delta["comments_count_delta"] * 2
        + latest_delta["saved_delta"] * 3
        + latest_delta["shares_delta"] * 4
    )

    top10 = latest_delta.sort_values("score", ascending=False).head(10)

    show_cols = [
        "media_type",
        "caption",
        "permalink",
        "views_delta",
        "like_count_delta",
        "comments_count_delta",
        "saved_delta",
        "shares_delta",
        "score"
    ]

    st.dataframe(
        top10[show_cols],
        use_container_width=True,
        hide_index=True
    )

st.divider()

st.subheader("전체 수집 데이터")

st.dataframe(
    media_df.sort_values("collected_at", ascending=False),
    use_container_width=True,
    hide_index=True
)

csv = media_df.to_csv(index=False).encode("utf-8-sig")

st.download_button(
    label="CSV 다운로드",
    data=csv,
    file_name="posetiz_instagram_monitor.csv",
    mime="text/csv"
)