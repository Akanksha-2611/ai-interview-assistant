import streamlit as st
from llm_utils import (
    extract_resume_text, generate_questions,
    evaluate_answer, followup_question, extract_score,
)

st.set_page_config(page_title="AI Interview Assistant", page_icon="🤖")
st.title("🤖 AI Interview Assistant")

# Initialize session state FIRST
for key, default in {"resume_text": "", "questions": "", "scores": []}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# 1. Upload resume
uploaded_file = st.file_uploader("Upload Resume", type=["pdf"])

if uploaded_file:
    st.session_state.resume_text = extract_resume_text(uploaded_file)
    st.success("✅ Resume uploaded successfully")

# 2. Generate questions
if st.button("Generate Questions"):
    if st.session_state.resume_text:
        with st.spinner("Generating questions..."):
            st.session_state.questions = generate_questions(
                st.session_state.resume_text
            )
    else:
        st.warning("Please upload a resume first.")

if st.session_state.questions:
    st.subheader("Generated Interview Questions")
    st.write(st.session_state.questions)

# 3. Answer a question
st.divider()
st.subheader("Practice Answering")

question = st.text_area("Paste the question you want to answer")
answer = st.text_area("Enter your answer")

col1, col2 = st.columns(2)

if col1.button("Evaluate Answer"):
    if question and answer:
        with st.spinner("Evaluating..."):
            feedback = evaluate_answer(question, answer)
        st.subheader("Feedback")
        st.write(feedback)
        score = extract_score(feedback)
        if score is not None:
            st.session_state.scores.append(score)
    else:
        st.warning("Enter both a question and an answer.")

if col2.button("Follow-up Question"):
    if question and answer:
        st.info(followup_question(question, answer))

# 4. Score tracking
if st.session_state.scores:
    avg = sum(st.session_state.scores) / len(st.session_state.scores)
    st.metric("Average Score", f"{avg:.1f} / 10")
    st.caption(f"Scores so far: {st.session_state.scores}")