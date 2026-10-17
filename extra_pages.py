import pandas as pd
import streamlit as st
from db import db_enabled, save_interview, fetch_leaderboard
from features import (
    generate_coding_problem, review_code, transcribe_verbatim,
    audio_duration, count_fillers, analyze_speech,
)

try:
    from streamlit_ace import st_ace
    HAS_ACE = True
except ImportError:
    HAS_ACE = False

LANGS = {
    "Python": "python", "Java": "java", "JavaScript": "javascript",
    "C++": "c_cpp", "SQL": "sql",
}
STARTER = {
    "Python": "# Write your solution here\n",
    "Java": "// Write your solution here\n",
    "JavaScript": "// Write your solution here\n",
    "C++": "// Write your solution here\n",
    "SQL": "-- Write your query here\n",
}
SPEAK_QUESTIONS = [
    "Tell me about yourself.",
    "Why do you want this role?",
    "Describe a challenging project you worked on.",
    "What is your biggest weakness?",
    "Where do you see yourself in five years?",
    "Write my own question...",
]


# ======================= CODING ROUND =======================
def coding_page():
    ss = st.session_state
    st.title("💻 Coding Round")
    st.caption("Write your solution and get an AI code review. "
               "The AI reads your code; it does not run it.")

    for k, v in {"cp_problem": None, "cp_review": None, "cp_n": 0,
                 "cp_asked": [], "cp_saved": False}.items():
        ss.setdefault(k, v)

    c1, c2, c3 = st.columns(3)
    language = c1.selectbox("Language", list(LANGS))
    difficulty = c2.selectbox("Difficulty", ["Easy", "Medium", "Hard"], index=1)
    role = c3.text_input("Role (optional)", key="cp_role")

    if st.button("🎲 New problem", type="primary"):
        with st.spinner("Creating a problem..."):
            p = generate_coding_problem(difficulty, language, role, ss.cp_asked)
        if p is None:
            st.error("Could not create a problem. Please try again.")
        else:
            ss.cp_problem = p
            ss.cp_review = None
            ss.cp_saved = False
            ss.cp_n += 1
            ss.cp_asked.append(p.get("title", ""))

    p = ss.cp_problem
    if not p:
        st.info("Click **New problem** to start.")
        return

    st.subheader(p.get("title", "Problem"))
    st.write(p.get("statement", ""))
    if p.get("example"):
        st.markdown("**Example**")
        st.code(p["example"], language="text")
    if p.get("constraints"):
        st.caption(f"Constraints: {p['constraints']}")
    with st.expander("💡 Hint"):
        st.write(p.get("hint", "No hint available."))

    key = f"ace_{ss.cp_n}"
    if HAS_ACE:
        code = st_ace(
            value=STARTER[language], language=LANGS[language],
            theme="monokai", height=320, font_size=14,
            auto_update=True, key=key,
        )
    else:
        code = st.text_area("Your code", value=STARTER[language], height=320, key=key)
    code = code or ""

    if st.button("🔍 Submit for AI review"):
        if not code.strip() or code.strip() == STARTER[language].strip():
            st.warning("Write your solution first.")
        else:
            with st.spinner("Reviewing your code..."):
                ss.cp_review = review_code(p, code, language)
            ss.cp_saved = False
            if ss.cp_review is None:
                st.error("Could not review the code. Please try again.")

    r = ss.cp_review
    if r:
        score = r["score"]
        (st.success if score >= 7 else st.warning if score >= 4 else st.error)(
            f"Score: {score} / 10 | {r.get('verdict', '')}"
        )
        st.markdown(f"**✅ Correctness:** {r.get('correctness', '')}")
        c1, c2 = st.columns(2)
        c1.markdown(f"**⏱️ Time:** {r.get('time_complexity', '')}")
        c2.markdown(f"**💾 Space:** {r.get('space_complexity', '')}")

        if r.get("bugs"):
            st.markdown("**🐞 Bugs / risks**")
            for b in r["bugs"]:
                st.markdown(f"- {b}")
        if r.get("improvements"):
            st.markdown("**🔧 Improvements**")
            for i in r["improvements"]:
                st.markdown(f"- {i}")
        with st.expander("📖 AI's suggested solution"):
            st.code(r.get("better_solution", ""), language=LANGS[language])

        if ss.get("user") and not ss.cp_saved:
            try:
                save_interview(role, "Coding", score, 10, [{
                    "question": p.get("title", "Coding problem"),
                    "score": score,
                    "missing_points": "; ".join(r.get("bugs", []))[:500] or "-",
                }])
                ss.cp_saved = True
            except Exception:
                pass
        if ss.cp_saved:
            st.caption("✅ Saved to your progress history")


# ======================= SPEAKING PRACTICE =======================
def speaking_page():
    ss = st.session_state
    st.title("🗣️ Speaking Practice")
    st.caption("Record your answer. The app transcribes it and counts filler "
               "words, speaking pace and clarity.")
    ss.setdefault("sp_n", 0)
    ss.setdefault("sp_result", None)

    choice = st.selectbox("Question", SPEAK_QUESTIONS)
    if choice == SPEAK_QUESTIONS[-1]:
        question = st.text_input("Your question") or "Tell me about yourself."
    else:
        question = choice
    st.markdown(f"### 🎤 {question}")

    audio = st.audio_input("Record your answer (aim for 30 to 90 seconds)",
                           key=f"sp_audio_{ss.sp_n}")

    if audio is not None and st.button("📊 Analyze my speech", type="primary"):
        data = audio.getvalue()
        duration = audio_duration(data)
        if 0 < duration < 3:
            st.warning("That recording is too short. Speak for at least a few seconds.")
        else:
            with st.spinner("Transcribing and analyzing..."):
                try:
                    transcript = transcribe_verbatim(data)
                except Exception:
                    transcript = ""
                if not transcript:
                    st.error("Could not transcribe the audio. Please try again.")
                else:
                    words = len(transcript.split())
                    wpm = round(words / (duration / 60)) if duration else 0
                    fillers = count_fillers(transcript)
                    total_f = sum(fillers.values())
                    ss.sp_result = {
                        "question": question, "transcript": transcript,
                        "duration": duration, "words": words, "wpm": wpm,
                        "fillers": fillers, "total_f": total_f,
                        "ai": analyze_speech(question, transcript, wpm, total_f),
                    }

    res = ss.sp_result
    if res:
        rate = res["total_f"] / res["words"] * 100 if res["words"] else 0
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Duration", f"{res['duration']:.0f}s")
        c2.metric("Words", res["words"])
        c3.metric("Pace", f"{res['wpm']} wpm" if res["wpm"] else "n/a")
        c4.metric("Fillers", f"{res['total_f']} ({rate:.1f}/100)")

        if res["wpm"]:
            if res["wpm"] < 110:
                st.info("Pace: a little slow. Aim for 120 to 160 words per minute.")
            elif res["wpm"] > 170:
                st.warning("Pace: fast. Slow down and pause between points.")
            else:
                st.success("Pace: good (120 to 160 wpm is ideal).")

        if res["fillers"]:
            st.markdown("**Filler words used**")
            st.bar_chart(res["fillers"])
            st.caption("Words like 'like' and 'actually' are only fillers when "
                       "they add no meaning, so treat this as an estimate.")
        else:
            st.success("No filler words detected. Great job!")

        ai = res.get("ai")
        if ai:
            a, b, c = st.columns(3)
            a.metric("Clarity", f"{ai.get('clarity', 0)}/10")
            b.metric("Structure", f"{ai.get('structure', 0)}/10")
            c.metric("Confidence", f"{ai.get('confidence', 0)}/10")
            st.write(ai.get("summary", ""))
            st.markdown("**Tips**")
            for t in ai.get("tips", []):
                st.markdown(f"- {t}")

        with st.expander("📝 Full transcript"):
            st.write(res["transcript"])

        if st.button("🔄 Record again"):
            ss.sp_n += 1
            ss.sp_result = None
            st.rerun()


# ======================= LEADERBOARD =======================
def leaderboard_page():
    st.title("🏆 Leaderboard")
    if not db_enabled():
        st.info("The leaderboard needs Supabase keys.")
        return

    mode = st.selectbox("Mode", ["All", "Technical", "HR", "Behavioral", "System Design"])
    try:
        rows = fetch_leaderboard(mode)
    except Exception as e:
        st.error(f"Could not load the leaderboard: {e}")
        return
    if not rows:
        st.info("No scores yet. Finish an interview and submit yours!")
        return

    best = {}
    for r in rows:
        name = r["nickname"]
        if name not in best or float(r["percent"]) > float(best[name]["percent"]):
            best[name] = r

    df = pd.DataFrame(list(best.values())).sort_values("percent", ascending=False)
    df = df.head(20).reset_index(drop=True)
    df["percent"] = df["percent"].astype(float).round(0).astype(int).astype(str) + "%"
    df.insert(0, "Rank", range(1, len(df) + 1))
    df = df.rename(columns={"nickname": "Name", "mode": "Mode",
                            "percent": "Score", "questions": "Questions"})
    st.dataframe(df[["Rank", "Name", "Mode", "Score", "Questions"]], hide_index=True)
    st.caption("Only interviews with 5+ questions can be submitted.")