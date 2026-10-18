import pandas as pd
import streamlit as st

from db import db_enabled, get_client


def is_admin():
    """True only for users listed in the Supabase `admins` table.

    The answer comes from the database (the is_admin() SQL function), so it
    cannot be faked from the browser. It is cached per logged-in user.
    """
    ss = st.session_state
    user = ss.get("user")
    if not db_enabled() or not user:
        return False

    cached = ss.get("_admin_cache")
    if cached and cached[0] == user.id:
        return cached[1]

    try:
        value = bool(get_client().rpc("is_admin", {}).execute().data)
    except Exception:
        value = False
    ss._admin_cache = (user.id, value)
    return value


def admin_page():
    st.title("🔧 Admin Dashboard")
    if not is_admin():
        st.error("This page is for admins only.")
        return

    client = get_client()
    try:
        rows = (client.table("interviews")
                .select("created_at,user_id,mode,role,percent")
                .order("created_at", desc=True)
                .limit(1000)
                .execute().data)
        board = client.table("leaderboard").select("id", count="exact").limit(1).execute()
    except Exception as e:
        st.error(f"Could not load stats: {e}")
        return

    if not rows:
        st.info("No sessions have been saved yet.")
        return

    df = pd.DataFrame(rows)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    df["percent"] = df["percent"].astype(float)
    df["role"] = df["role"].fillna("General")

    week_ago = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=7)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sessions", len(df))
    c2.metric("Users", df["user_id"].nunique())
    c3.metric("Last 7 days", int((df["created_at"] >= week_ago).sum()))
    c4.metric("Leaderboard entries", board.count or 0)
    st.caption("Based on the latest 1,000 saved sessions. Emails are never shown here.")

    st.markdown("#### Sessions per day")
    per_day = df.groupby(df["created_at"].dt.date).size()
    st.bar_chart(per_day)

    left, right = st.columns(2)
    with left:
        st.markdown("#### Sessions by mode")
        st.bar_chart(df["mode"].value_counts())
    with right:
        st.markdown("#### Average score by mode")
        st.bar_chart(df.groupby("mode")["percent"].mean().round(1))

    st.markdown("#### Most practiced roles")
    st.dataframe(
        df["role"].value_counts().head(10).rename_axis("Role").reset_index(name="Sessions"),
        hide_index=True,
    )