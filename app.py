import streamlit as st
from llm_utils import (
    extract_resume_text, generate_question_list,
    evaluate_answer, followup_question, generate_final_report,
)

st.set_page_config(page_title="AI Interview Assistant v2.0", page_icon="🤖")
st.title("🤖 AI Interview Assistant v2.0")

# ---------- Session state ----------
defaults = {
    "stage": "setup",      # setup -> interview -> result
    "resume_text": "",
    "questions": [],
    "current": 0,
    "results": [],
    "evaluated": False,
    "last_feedback": None,
    "followup": "",
    "report": "",
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


def restart():
    for key, value in defaults.items():
        st.session_state[key] = value
    for k in list(st.session_state.keys()):
        if k.startswith("answer_"):
            del st.session_state[k]


# ---------- Stage 1: Setup ----------
if st.session_state.stage == "setup":
    st.subheader("Step 1: Upload your resume")
    uploaded_file = st.file_uploader("Upload Resume (PDF)", type=["pdf"])

    col1, col2 = st.columns(2)
    num_q = col1.slider("Number of questions", 3, 15, 5)
    difficulty = col2.selectbox("Difficulty", ["Easy", "Medium", "Hard"], index=1)

    if st.button("🚀 Start Interview", type="primary"):
        if not uploaded_file:
            st.warning("Please upload a resume first.")
        else:
            with st.spinner("Reading resume and preparing questions..."):
                text = extract_resume_text(uploaded_file)
                questions = generate_question_list(text, num_q, difficulty)
            if not questions:
                st.error("Could not generate questions. Please try again.")
            else:
                st.session_state.resume_text = text
                st.session_state.questions = questions
                st.session_state.stage = "interview"
                st.rerun()

# ---------- Stage 2: Interview ----------
elif st.session_state.stage == "interview":
    idx = st.session_state.current
    total = len(st.session_state.questions)
    q = st.session_state.questions[idx]

    st.progress(idx / total, text=f"Question {idx + 1} of {total}")
    if st.session_state.results:
        running = sum(r["score"] for r in st.session_state.results) / len(
            st.session_state.results
        )
        st.caption(f"Running average: {running:.1f} / 10")

    st.markdown(f"### 🎤 {q['question']}")
    st.caption(f"Type: {q['type']}")

    answer = st.text_area(
        "Your answer",
        key=f"answer_{idx}",
        height=180,
        disabled=st.session_state.evaluated,
    )

    # Before evaluation
    if not st.session_state.evaluated:
        col1, col2 = st.columns(2)
        if col1.button("✅ Submit Answer", type="primary"):
            if not answer.strip():
                st.warning("Please write an answer, or click Skip.")
            else:
                with st.spinner("Evaluating your answer..."):
                    fb = evaluate_answer(q["question"], answer)
                st.session_state.last_feedback = fb
                st.session_state.results.append({
                    "type": q["type"],
                    "question": q["question"],
                    "answer": answer,
                    **fb,
                })
                st.session_state.evaluated = True
                st.rerun()

        if col2.button("⏭️ Skip"):
            st.session_state.results.append({
                "type": q["type"],
                "question": q["question"],
                "answer": "(skipped)",
                "score": 0,
                "strengths": "-",
                "missing_points": "Question skipped.",
                "ideal_answer": "",
            })
            st.session_state.current += 1
            if st.session_state.current >= total:
                st.session_state.stage = "result"
            st.rerun()

    # After evaluation
    else:
        fb = st.session_state.last_feedback
        score = fb["score"]
        if score >= 7:
            st.success(f"Score: {score} / 10")
        elif score >= 4:
            st.warning(f"Score: {score} / 10")
        else:
            st.error(f"Score: {score} / 10")

        st.markdown(f"**💪 Strengths:** {fb['strengths']}")
        st.markdown(f"**⚠️ Missing points:** {fb['missing_points']}")
        with st.expander("📖 See ideal answer"):
            st.write(fb["ideal_answer"])

        if st.button("🔁 Get a follow-up question"):
            st.session_state.followup = followup_question(
                q["question"], answer
            )
        if st.session_state.followup:
            st.info(f"Follow-up (for practice): {st.session_state.followup}")

        is_last = idx + 1 >= total
        label = "🏁 Finish Interview" if is_last else "➡️ Next Question"
        if st.button(label, type="primary"):
            st.session_state.current += 1
            st.session_state.evaluated = False
            st.session_state.last_feedback = None
            st.session_state.followup = ""
            if is_last:
                st.session_state.stage = "result"
            st.rerun()

# ---------- Stage 3: Final result ----------
elif st.session_state.stage == "result":
    results = st.session_state.results
    total_score = sum(r["score"] for r in results)
    max_score = len(results) * 10
    percent = total_score / max_score * 100 if max_score else 0

    st.subheader("🏆 Final Result")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Score", f"{total_score} / {max_score}")
    c2.metric("Average", f"{total_score / len(results):.1f} / 10")
    c3.metric("Percentage", f"{percent:.0f}%")

    st.bar_chart({f"Q{i+1}": r["score"] for i, r in enumerate(results)})

    if not st.session_state.report:
        with st.spinner("Writing your final report..."):
            st.session_state.report = generate_final_report(results)
    st.markdown("### 📝 AI Feedback Report")
    st.write(st.session_state.report)

    st.markdown("### 📋 Question-wise Breakdown")
    for i, r in enumerate(results):
        with st.expander(f"Q{i+1}: {r['question']}  —  {r['score']}/10"):
            st.markdown(f"**Your answer:** {r['answer']}")
            st.markdown(f"**Strengths:** {r['strengths']}")
            st.markdown(f"**Missing points:** {r['missing_points']}")
            st.markdown(f"**Ideal answer:** {r['ideal_answer']}")

    # Download report
    lines = [f"AI Interview Report\nTotal: {total_score}/{max_score} ({percent:.0f}%)\n"]
    for i, r in enumerate(results):
        lines.append(
            f"\nQ{i+1}. {r['question']}\nAnswer: {r['answer']}\n"
            f"Score: {r['score']}/10\nMissing: {r['missing_points']}\n"
            f"Ideal: {r['ideal_answer']}\n"
        )
    lines.append("\n--- AI Report ---\n" + st.session_state.report)
    st.download_button(
        "⬇️ Download Report",
        "\n".join(lines),
        file_name="interview_report.txt",
    )

    if st.button("🔄 Start New Interview"):
        restart()
        st.rerun()