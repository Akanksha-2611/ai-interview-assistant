import time
import pandas as pd
import streamlit as st
from llm_utils import (
    MODES, extract_resume_text, generate_next_question, evaluate_answer,
    followup_question, generate_final_report, transcribe_audio,
    adjust_difficulty, build_pdf, analyze_resume,
)
from db import (
    db_enabled, sign_up, sign_in, sign_out, save_interview, fetch_history,
)

st.set_page_config(page_title="AI Interview Assistant v4.0", page_icon="🤖")

defaults = {
    "stage": "setup",
    "resume_text": "",
    "job_desc": "",
    "role": "",
    "mode": "Technical",
    "total_q": 5,
    "time_limit": 180,
    "difficulty": "Medium",
    "questions": [],
    "current": 0,
    "results": [],
    "evaluated": False,
    "last_feedback": None,
    "followup": "",
    "report": "",
    "q_start": None,
    "saved": False,
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


def restart():
    for key, value in defaults.items():
        st.session_state[key] = value
    for k in list(st.session_state.keys()):
        if k.startswith(("answer_", "audio_")):
            del st.session_state[k]


def advance(last_score):
    ss = st.session_state
    ss.current += 1
    ss.evaluated = False
    ss.last_feedback = None
    ss.followup = ""
    ss.q_start = None

    if ss.current >= ss.total_q:
        ss.stage = "result"
        return

    ss.difficulty = adjust_difficulty(ss.difficulty, last_score)
    types = MODES[ss.mode]["types"]
    with st.spinner(f"Preparing a {ss.difficulty} question..."):
        nq = generate_next_question(
            ss.resume_text, ss.job_desc, ss.role, ss.difficulty,
            types[ss.current % len(types)],
            [q["question"] for q in ss.questions], ss.mode,
        )
    if nq is None:
        st.warning("Could not generate the next question. Ending the interview.")
        ss.stage = "result"
    else:
        ss.questions.append(nq)


@st.fragment(run_every=1)
def countdown(start, limit):
    """Live timer: only this small block refreshes every second."""
    left = int(limit - (time.time() - start))
    if left > 0:
        m, s = divmod(left, 60)
        st.markdown(f"⏳ **Time left: {m:02d}:{s:02d}**")
    else:
        st.markdown(":red[⏰ **Time's up!** Please wrap up your answer.]")

def auth_page():
    st.markdown("<br>", unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.title("🤖 AI Interview Assistant")
        st.caption("Practice interviews, review your resume, and track your progress.")

        tab_login, tab_signup = st.tabs(["Log in", "Sign up"])

        with tab_login:
            email = st.text_input("Email", key="li_email")
            password = st.text_input("Password", type="password", key="li_pass")
            if st.button("Log in", type="primary", use_container_width=True):
                try:
                    sign_in(email, password)
                    st.rerun()
                except Exception as e:
                    st.error(f"Login failed: {e}")

        with tab_signup:
            email2 = st.text_input("Email", key="su_email")
            password2 = st.text_input("Password (min 6 characters)",
                                      type="password", key="su_pass")
            if st.button("Create account", type="primary", use_container_width=True):
                try:
                    sign_up(email2, password2)
                    st.success("Account created. Now switch to the Log in tab "
                               "(confirm your email first if asked).")
                except Exception as e:
                    st.error(f"Sign up failed: {e}")

        st.divider()
        if st.button("Continue as guest (history won't be saved)",
                     use_container_width=True):
            st.session_state.guest = True
            st.rerun()

# ======================= SIDEBAR =======================
def sidebar():
    st.sidebar.title("🤖 AI Interview")
    page = st.sidebar.radio(
        "Menu", ["🎤 Mock Interview", "📄 Resume Review", "📈 My Progress"]
    )
    st.sidebar.divider()

    user = st.session_state.get("user")
    if user:
        st.sidebar.success(f"Logged in as {user.email}")
        if st.sidebar.button("Log out"):
            sign_out()
            st.session_state.pop("guest", None)
            st.rerun()
    else:
        st.sidebar.info("Guest mode: results are not saved.")
        if st.sidebar.button("Log in / Sign up"):
            st.session_state.pop("guest", None)
            st.rerun()
    return page


# ======================= PAGE: INTERVIEW =======================
def interview_page():
    ss = st.session_state
    st.title("🎤 Mock Interview")

    # ---------- Setup ----------
    if ss.stage == "setup":
        uploaded_file = st.file_uploader("Upload Resume (PDF)", type=["pdf"])
        mode = st.selectbox("Interview mode", list(MODES.keys()))
        role = st.text_input("Target role (optional)", placeholder="e.g. Python Developer")
        job_desc = st.text_area("Paste job description (optional)", height=120)

        c1, c2, c3 = st.columns(3)
        num_q = c1.slider("Questions", 3, 15, 5)
        difficulty = c2.selectbox("Starting difficulty", ["Easy", "Medium", "Hard"], index=1)
        time_limit = c3.slider("Seconds per question", 60, 300, 180, step=30)
        st.caption("Difficulty adapts automatically based on your scores.")

        if st.button("🚀 Start Interview", type="primary"):
            if not uploaded_file:
                st.warning("Please upload a resume first.")
            else:
                with st.spinner("Reading resume and preparing the first question..."):
                    text = extract_resume_text(uploaded_file)
                    first = generate_next_question(
                        text, job_desc, role, difficulty,
                        MODES[mode]["types"][0], [], mode,
                    )
                if first is None:
                    st.error("Could not generate a question. Please try again.")
                else:
                    ss.update(
                        resume_text=text, job_desc=job_desc, role=role,
                        mode=mode, total_q=num_q, time_limit=time_limit,
                        difficulty=difficulty, questions=[first],
                        stage="interview",
                    )
                    st.rerun()

    # ---------- Interview ----------
    elif ss.stage == "interview":
        idx = ss.current
        total = ss.total_q
        q = ss.questions[idx]

        if ss.q_start is None:
            ss.q_start = time.time()

        st.progress(idx / total, text=f"Question {idx + 1} of {total}")
        if ss.results:
            running = sum(r["score"] for r in ss.results) / len(ss.results)
            st.caption(f"Running average: {running:.1f} / 10")

        st.markdown(f"### {q['question']}")
        st.caption(f"Mode: {ss.mode}  |  Type: {q['type']}  |  Difficulty: {q['difficulty']}")

        if not ss.evaluated:
            countdown(ss.q_start, ss.time_limit)
            audio = st.audio_input("🎙️ Or record your answer", key=f"audio_{idx}")
            if audio is not None and st.button("📝 Transcribe recording"):
                with st.spinner("Transcribing..."):
                    try:
                        ss[f"answer_{idx}"] = transcribe_audio(audio.getvalue())
                    except Exception:
                        st.error("Could not transcribe. Please type your answer instead.")

        answer = st.text_area(
            "Your answer", key=f"answer_{idx}", height=180, disabled=ss.evaluated
        )

        if not ss.evaluated:
            col1, col2 = st.columns(2)
            if col1.button("✅ Submit Answer", type="primary"):
                if not answer.strip():
                    st.warning("Please write an answer, or click Skip.")
                else:
                    taken = int(time.time() - ss.q_start)
                    with st.spinner("Evaluating your answer..."):
                        fb = evaluate_answer(
                            q["question"], answer, ss.role, ss.job_desc, ss.mode
                        )
                    ss.last_feedback = fb
                    ss.results.append({
                        "type": q["type"], "difficulty": q["difficulty"],
                        "question": q["question"], "answer": answer,
                        "time_taken": taken, **fb,
                    })
                    ss.evaluated = True
                    st.rerun()

            if col2.button("⏭️ Skip"):
                ss.results.append({
                    "type": q["type"], "difficulty": q["difficulty"],
                    "question": q["question"], "answer": "(skipped)",
                    "score": 0, "strengths": "-",
                    "missing_points": "Question skipped.", "ideal_answer": "",
                    "time_taken": int(time.time() - ss.q_start),
                })
                advance(None)
                st.rerun()
        else:
            fb = ss.last_feedback
            score = fb["score"]
            taken = ss.results[-1]["time_taken"]

            if score >= 7:
                st.success(f"Score: {score} / 10")
            elif score >= 4:
                st.warning(f"Score: {score} / 10")
            else:
                st.error(f"Score: {score} / 10")

            over = " (over the time limit)" if taken > ss.time_limit else ""
            st.caption(f"⏱️ Time taken: {taken}s{over}")

            st.markdown(f"**💪 Strengths:** {fb['strengths']}")
            st.markdown(f"**⚠️ Missing points:** {fb['missing_points']}")
            with st.expander("📖 See ideal answer"):
                st.write(fb["ideal_answer"])

            if st.button("🔁 Get a follow-up question"):
                ss.followup = followup_question(q["question"], answer)
            if ss.followup:
                st.info(f"Follow-up (for practice): {ss.followup}")

            is_last = idx + 1 >= total
            label = "🏁 Finish Interview" if is_last else "➡️ Next Question"
            if st.button(label, type="primary"):
                advance(score)
                st.rerun()

    # ---------- Result ----------
    elif ss.stage == "result":
        results = ss.results
        if not results:
            st.warning("No answers were recorded.")
            if st.button("🔄 Start New Interview"):
                restart()
                st.rerun()
            return

        total_score = sum(r["score"] for r in results)
        max_score = len(results) * 10
        percent = total_score / max_score * 100 if max_score else 0

        st.subheader("🏆 Final Result")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Score", f"{total_score} / {max_score}")
        c2.metric("Average", f"{total_score / len(results):.1f} / 10")
        c3.metric("Percentage", f"{percent:.0f}%")
        c4.metric("Avg Time", f"{sum(r['time_taken'] for r in results) // len(results)}s")

        st.bar_chart({f"Q{i+1}": r["score"] for i, r in enumerate(results)})

        if not ss.report:
            with st.spinner("Writing your final report..."):
                ss.report = generate_final_report(results, ss.role, ss.mode)
        st.markdown("### 📝 AI Feedback Report")
        st.write(ss.report)

        # Save to history
        if not ss.saved:
            if st.session_state.get("user"):
                try:
                    save_interview(ss.role, ss.mode, total_score, max_score, results)
                    ss.saved = True
                    st.success("✅ Saved to your progress history")
                except Exception as e:
                    st.warning(f"Could not save to history: {e}")
            elif db_enabled():
                st.info("Log in from the sidebar to save this result to your history.")
        else:
            st.success("✅ Saved to your progress history")

        st.markdown("### 📋 Question-wise Breakdown")
        for i, r in enumerate(results):
            with st.expander(f"Q{i+1} ({r['difficulty']}): {r['question']}  —  {r['score']}/10"):
                st.markdown(f"**Your answer:** {r['answer']}")
                st.markdown(f"**Time taken:** {r['time_taken']}s")
                st.markdown(f"**Strengths:** {r['strengths']}")
                st.markdown(f"**Missing points:** {r['missing_points']}")
                st.markdown(f"**Ideal answer:** {r['ideal_answer']}")

        st.download_button(
            "⬇️ Download PDF Report",
            build_pdf(results, ss.report, ss.role, ss.mode, total_score, max_score),
            file_name="interview_report.pdf",
            mime="application/pdf",
        )

        if st.button("🔄 Start New Interview"):
            restart()
            st.rerun()


# ======================= PAGE: RESUME REVIEW =======================
def resume_page():
    st.title("📄 Resume Review")
    st.caption("Get an ATS-style score and concrete improvements.")

    file = st.file_uploader("Upload Resume (PDF)", type=["pdf"], key="rv_file")
    role = st.text_input("Target role (optional)", key="rv_role")
    jd = st.text_area("Paste job description (optional)", height=120, key="rv_jd")

    if st.button("🔍 Analyze Resume", type="primary"):
        if not file:
            st.warning("Please upload a resume first.")
            return
        with st.spinner("Analyzing your resume..."):
            text = extract_resume_text(file)
            data = analyze_resume(text, role, jd)
        if not data:
            st.error("Could not analyze the resume. Please try again.")
            return

        score = data["ats_score"]
        st.metric("ATS Score", f"{score} / 100")
        st.progress(score / 100)
        st.write(data.get("summary", ""))

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### 💪 Strengths")
            for s in data.get("strengths", []):
                st.markdown(f"- {s}")
        with c2:
            st.markdown("#### ⚠️ Weaknesses")
            for s in data.get("weaknesses", []):
                st.markdown(f"- {s}")

        st.markdown("#### 🔑 Missing Keywords")
        st.write(", ".join(data.get("missing_keywords", [])) or "None found")

        st.markdown("#### ✅ Suggestions")
        for s in data.get("suggestions", []):
            st.markdown(f"- {s}")


# ======================= PAGE: PROGRESS =======================
def progress_page():
    st.title("📈 My Progress")

    if not db_enabled():
        st.info("History is disabled. Add Supabase keys to enable it.")
        return
    if not st.session_state.get("user"):
        st.info("Log in from the sidebar to see your history.")
        return

    try:
        rows = fetch_history()
    except Exception as e:
        st.error(f"Could not load history: {e}")
        return
    if not rows:
        st.info("No interviews saved yet. Finish a mock interview first.")
        return

    df = pd.DataFrame(rows)
    df["created_at"] = pd.to_datetime(df["created_at"])
    df["percent"] = df["percent"].astype(float)

    c1, c2, c3 = st.columns(3)
    c1.metric("Interviews", len(df))
    c2.metric("Best Score", f"{df['percent'].max():.0f}%")
    c3.metric("Average", f"{df['percent'].mean():.0f}%")

    st.markdown("#### Score trend")
    st.line_chart(df.sort_values("created_at").set_index("created_at")["percent"])

    st.markdown("#### Past interviews")
    for r in rows:
        when = pd.to_datetime(r["created_at"]).strftime("%d %b %Y, %H:%M")
        title = f"{when} | {r['mode']} | {r['role']} | {float(r['percent']):.0f}%"
        with st.expander(title):
            for i, d in enumerate(r["details"] or []):
                st.markdown(f"**Q{i+1}. {d['question']}** — {d['score']}/10")
                st.caption(f"Missing: {d['missing_points']}")



# ======================= ROUTER =======================
logged_in = st.session_state.get("user") is not None
is_guest = st.session_state.get("guest", False)

if db_enabled() and not (logged_in or is_guest):
    auth_page()
else:
    page = sidebar()
    if page == "🎤 Mock Interview":
        interview_page()
    elif page == "📄 Resume Review":
        resume_page()
    else:
        progress_page()