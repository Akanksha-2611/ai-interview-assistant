import os
import streamlit as st
from supabase import create_client


def _secret(name):
    value = os.getenv(name)
    if value:
        return value
    try:
        return st.secrets[name]
    except Exception:
        return None


def db_enabled():
    return bool(_secret("SUPABASE_URL") and _secret("SUPABASE_KEY"))


def get_client():
    # One client PER user session (never share one login between visitors)
    if "sb" not in st.session_state:
        st.session_state.sb = create_client(
            _secret("SUPABASE_URL"), _secret("SUPABASE_KEY")
        )
    return st.session_state.sb


def sign_up(email, password):
    return get_client().auth.sign_up({"email": email, "password": password})


def sign_in(email, password):
    res = get_client().auth.sign_in_with_password(
        {"email": email, "password": password}
    )
    st.session_state.user = res.user


def sign_out():
    try:
        get_client().auth.sign_out()
    except Exception:
        pass
    st.session_state.pop("sb", None)
    st.session_state.pop("user", None)


def save_interview(role, mode, total_score, max_score, results):
    user = st.session_state.get("user")
    if not user:
        return
    percent = round(total_score / max_score * 100, 1) if max_score else 0
    get_client().table("interviews").insert({
        "user_id": user.id,
        "role": role or "General",
        "mode": mode,
        "total_score": total_score,
        "max_score": max_score,
        "percent": percent,
        "details": results,
    }).execute()


def fetch_history():
    res = (
        get_client()
        .table("interviews")
        .select("*")
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return res.data