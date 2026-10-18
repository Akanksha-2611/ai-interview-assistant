"""Stay logged in after a browser refresh.

How it works
- After login, the Supabase refresh token is saved in a browser cookie.
- On a fresh page load, st.context.cookies lets the server read that cookie
  and ask Supabase for a new session (no extra package needed).
- Supabase rotates refresh tokens, so the cookie is rewritten whenever the
  token changes. Logging out deletes it.

If anything here fails, the user simply sees the normal login page.
"""
import json
import urllib.parse

import streamlit as st
import streamlit.components.v1 as components

from db import db_enabled, get_client

COOKIE = "sb_rt"
DAYS = 7


def _write_cookie(value):
    """Set (or delete, when value is empty) the cookie from the browser side."""
    max_age = DAYS * 86400 if value else 0
    encoded = json.dumps(urllib.parse.quote(value or "", safe=""))
    components.html(
        f"""
        <script>
        try {{
          const p = window.parent;
          const secure = p.location.protocol === "https:" ? "; Secure" : "";
          p.document.cookie = "{COOKIE}=" + {encoded}
            + "; path=/; max-age={max_age}; SameSite=Lax" + secure;
        }} catch (e) {{}}
        </script>
        """,
        height=0,
    )


def restore_session():
    """Run once per browser session, before deciding whether to show login."""
    ss = st.session_state
    if ss.get("user") or ss.get("restore_tried") or not db_enabled():
        return
    ss.restore_tried = True

    try:
        raw = st.context.cookies.get(COOKIE)
    except Exception:
        raw = None
    if not raw:
        return

    try:
        res = get_client().auth.refresh_session(urllib.parse.unquote(raw))
        if res and res.user:
            ss.user = res.user
            ss.cookie_rt = None  # force the rotated token to be saved
            return
    except Exception:
        pass
    ss.pending_clear = True  # token was invalid or expired


def sync_cookie():
    """Call at the end of every run: keeps the cookie in step with the session."""
    ss = st.session_state
    if ss.get("pending_clear"):
        ss.pending_clear = False
        ss.cookie_rt = None
        _write_cookie("")
        return
    if not ss.get("user"):
        return
    try:
        session = get_client().auth.get_session()
        token = session.refresh_token if session else None
    except Exception:
        token = None
    if token and token != ss.get("cookie_rt"):
        _write_cookie(token)
        ss.cookie_rt = token


def request_clear():
    st.session_state.pending_clear = True