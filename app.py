import time
import streamlit as st
from llm_utils import (
    extract_resume_text, generate_next_question, evaluate_answer,
    followup_question, generate_final_report, transcribe_audio,
    adjust_difficulty, build_pdf,
)

st.set_page_config(page_title="AI Interview Assistant v3.0", page_icon="🤖")
st.title("🤖 AI Interview Assistant v3.0")

TYPES = ["Technical", "Project-Based", "Scenario-Based"]
TIME_LIMIT = 180  # seconds per question (soft limit, shown in the report)

defaults = {
    "stage": "setup",
    "resume_text": "",
    "job_desc": "",
    "role": "",
    "total_q": 5,
    "difficulty": "Medium",
    "questions": [],
    "current": 0,
    "results": [],
    "evaluated": False,
    "last_feedback": None,
    "followup": "",
    "report": "",
    "q_start": None,
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
    """Move to the next question, adjusting difficulty from the last score."""
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
    with st.spinner(f"Preparing a {ss.difficulty} question..."):
        nq = generate_next_question(
            ss.resume_text, ss.job_desc, ss.role, ss.difficulty,
            TYPES[ss.current % len(TYPES)],
            [q["question"] for q in ss.questions],
        )
    if nq is None:
        st.warning("Could not generate the next question. Ending the interview.")
        ss.stage = "result"
    else:
        ss.questions.append(nq)


# ---------- Stage 1: Setup ----------
if st.session_state.stage == "setup":
    st.subheader("Step 1: Tell us about the interview")
    uploaded_file = st.file_uploader("Upload Resume (PDF)", type=["pdf"])
    role = st.text_input("Target role (optional)", placeholder="e.g. Python Developer")
    job_desc = st.text_area("Paste job description (optional)", height=150)

    col1, col2 = st.columns(2)
    num_q = col1.slider("Number of questions", 3, 15, 5)
    difficulty = col2.selectbox("Starting difficulty", ["Easy", "Medium", "Hard"], index=1)
    st.caption("Difficulty adapts automatically based on your scores.")

    if st.button("🚀 Start Interview", type="primary"):
        if not uploaded_file:
            st.warning("Please upload a resume first.")
        else:
            with st.spinner("Reading resume and preparing the first question..."):
                text = extract_resume_text(uploaded_file)
                first = generate_next_question(
                    text, job_desc, role, difficulty, TYPES[0], []
                )
            if first is None:
                st.error("Could not generate a question. Please try again.")
            else:
                st.session_state.update(
                    resume_text=text, job_desc=job_desc, role=role,
                    total_q=num_q, difficulty=difficulty,
                    questions=[first], stage="interview",
                )
                st.rerun()

# ---------- Stage 2: Interview ----------
elif st.session_state.stage == "interview":
    ss = st.session_state
    idx = ss.current
    total = ss.total_q
    q = ss.questions[idx]

    if ss.q_start is None:
        ss.q_start = time.time()

    st.progress(idx / total, text=f"Question {idx + 1} of {total}")
    if ss.results:
        running = sum(r["score"] for r in ss.results) / len(ss.results)
        st.caption(f"Running average: {running:.1f} / 10")

    st.markdown(f"### 🎤 {q['question']}")
    st.caption(f"Type: {q['type']}  |  Difficulty: {q['difficulty']}")

    # Voice answer (before the text box so it can fill it in)
    if not ss.evaluated:
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
                    fb = evaluate_answer(q["question"], answer, ss.role, ss.job_desc)
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
                "score": 0, "strengths": "-", "missing_points": "Question skipped.",
                "ideal_answer": "", "time_taken": int(time.time() - ss.q_start),
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

        if taken > TIME_LIMIT:
            st.caption(f"⏱️ Time taken: {taken}s (over the {TIME_LIMIT}s target)")
        else:
            st.caption(f"⏱️ Time taken: {taken}s")

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

# ---------- Stage 3: Final result ----------
elif st.session_state.stage == "result":
    ss = st.session_state
    results = ss.results
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
            ss.report = generate_final_report(results, ss.role)
    st.markdown("### 📝 AI Feedback Report")
    st.write(ss.report)

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
        build_pdf(results, ss.report, ss.role, total_score, max_score),
        file_name="interview_report.pdf",
        mime="application/pdf",
    )

    if st.button("🔄 Start New Interview"):
        restart()
        st.rerun()