import streamlit as st

from admin_page import admin_page, is_admin
from core_pages import interview_page, progress_page, resume_page
from db import db_enabled, sign_in, sign_out, sign_up
from extra_pages import coding_page, leaderboard_page, speaking_page
from resilient import LLMBusyError
from session_persist import request_clear, restore_session, sync_cookie
from toolkit_pages import toolkit_page

st.set_page_config(page_title="AI Interview Assistant v6.0", page_icon="🤖")

st.markdown(
    "<style>footer {visibility: hidden;} "
    ".block-container {padding-top: 2rem;}</style>",
    unsafe_allow_html=True,
)


# ======================= LOGIN PAGE =======================
def auth_page():
    st.markdown("<br>", unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.title("🤖 AI Interview Assistant")
        st.caption("Mock interviews, coding practice, resume tools and progress tracking.")

        tab_login, tab_signup = st.tabs(["Log in", "Sign up"])

        with tab_login:
            email = st.text_input("Email", key="li_email")
            password = st.text_input("Password", type="password", key="li_pass")
            if st.button("Log in", type="primary"):
                try:
                    sign_in(email, password)
                    st.rerun()
                except Exception as e:
                    st.error(f"Login failed: {e}")

        with tab_signup:
            email2 = st.text_input("Email", key="su_email")
            password2 = st.text_input("Password (min 6 characters)",
                                      type="password", key="su_pass")
            if st.button("Create account", type="primary"):
                try:
                    sign_up(email2, password2)
                    st.success("Account created. Now switch to the Log in tab "
                               "(confirm your email first if asked).")
                except Exception as e:
                    st.error(f"Sign up failed: {e}")

        st.divider()
        if st.button("Continue as guest (history won't be saved)"):
            st.session_state.guest = True
            st.rerun()


# ======================= SIDEBAR ACCOUNT BOX =======================
def logout():
    sign_out()
    # Forget everything from this session so the next person starts clean.
    for key in list(st.session_state.keys()):
        try:
            del st.session_state[key]
        except Exception:
            pass
    st.session_state.restore_tried = True  # do not auto-login from the old cookie
    request_clear()
    st.rerun()


def account_box():
    with st.sidebar:
        st.divider()
        user = st.session_state.get("user")
        if user:
            st.success(f"Logged in as {user.email}")
            if st.button("Log out"):
                logout()
        else:
            st.info("Guest mode: results are not saved.")
            if st.button("Log in / Sign up"):
                st.session_state.pop("guest", None)
                st.rerun()


# ======================= NAVIGATION =======================
def build_pages():
    pages = {
        "Practice": [
            st.Page(interview_page, title="Mock Interview", icon="🎤",
                    url_path="interview", default=True),
            st.Page(coding_page, title="Coding Round", icon="💻", url_path="coding"),
            st.Page(speaking_page, title="Speaking Practice", icon="📢",
                    url_path="speaking"),
        ],
        "Career": [
            st.Page(toolkit_page, title="Career Toolkit", icon="🧰", url_path="toolkit"),
            st.Page(resume_page, title="Resume Review", icon="📄", url_path="resume"),
        ],
        "Progress": [
            st.Page(progress_page, title="My Progress", icon="📈", url_path="progress"),
            st.Page(leaderboard_page, title="Leaderboard", icon="🏆",
                    url_path="leaderboard"),
        ],
    }
    if is_admin():
        pages["Progress"].append(
            st.Page(admin_page, title="Admin", icon="🔧", url_path="admin"))
    return pages


# ======================= ROUTER =======================
restore_session()  # brings back a login after a browser refresh

logged_in = st.session_state.get("user") is not None
is_guest = st.session_state.get("guest", False)

if db_enabled() and not (logged_in or is_guest):
    auth_page()
    sync_cookie()
    st.stop()

page = st.navigation(build_pages())
account_box()

try:
    page.run()
except LLMBusyError as e:
    st.error(f"⏳ {e}")
    if st.button("🔄 Try again"):
        st.rerun()

sync_cookie()