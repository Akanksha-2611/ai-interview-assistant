import random

import streamlit as st

from db import save_interview
from features import _loose_json
from llm_utils import extract_resume_text, llm
from resilient import LLMBusyError
from toolkit_logic import (
    cover_letter_prompt, negotiation_feedback_prompt, normalize_quiz,
    quiz_prompt, recruiter_ceiling, recruiter_prompt, rewrite_analysis_prompt,
    rewrite_resume_prompt, text_to_pdf,
)

MAX_TURNS = 8


def _ask(prompt):
    return llm.invoke(prompt).text.strip()


def _ask_json(prompt):
    return _loose_json(llm.invoke(prompt).text)


def _fail(err):
    if isinstance(err, LLMBusyError):
        st.error(f"⏳ {err}")
    else:
        st.error("Something went wrong. Please try again.")


def _dict(value):
    return value if isinstance(value, dict) else {}


def _save(role, mode, total, max_score, details):
    """Save to history when logged in. Returns True if saved."""
    if not st.session_state.get("user"):
        return False
    try:
        save_interview(role, mode, total, max_score, details)
        return True
    except Exception:
        return False


# ======================================================== shared details box
def _details_block():
    ss = st.session_state
    resume = ss.get("tk_resume") or ss.get("resume_text") or ""

    with st.expander("📎 Your details (used by every tab)", expanded=not resume):
        file = st.file_uploader("Resume (PDF)", type=["pdf"], key="tk_file")
        if file is not None:
            try:
                text = extract_resume_text(file)
            except Exception:
                text = ""
            if text.strip():
                ss.tk_resume = text
                resume = text
            else:
                st.warning("Could not read text from this PDF. Scanned images "
                           "need a text-based PDF.")
        c1, c2 = st.columns(2)
        c1.text_input("Your name", key="tk_name")
        c2.text_input("Target role", key="tk_role", placeholder="e.g. Python Developer")
        c1.text_input("Company", key="tk_company", placeholder="e.g. Infosys")
        st.text_area("Job description (recommended)", key="tk_jd", height=140)

    if resume:
        st.caption(f"✅ Resume loaded ({len(resume.split())} words)")
    return resume


# ============================================================ resume rewriter
def _rewriter_tab(resume, role, jd):
    ss = st.session_state
    st.caption("Sharpens your wording and tailors it to the job. It only uses "
               "facts from your resume.")

    if st.button("✨ Rewrite and tailor my resume", type="primary", key="rw_btn"):
        if not resume:
            st.warning("Upload your resume in 'Your details' first.")
        else:
            try:
                with st.spinner("Analyzing your resume..."):
                    analysis = _ask_json(rewrite_analysis_prompt(resume, role, jd))
                with st.spinner("Writing the tailored version..."):
                    text = _ask(rewrite_resume_prompt(resume, role, jd))
                ss.tk_rw = _dict(analysis)
                ss.rw_text = text
            except Exception as e:
                _fail(e)

    data = ss.get("tk_rw")
    if data is None:
        return

    if data.get("summary"):
        st.markdown("#### Suggested summary")
        st.write(data["summary"])

    bullets = data.get("bullets") or []
    if bullets:
        st.markdown("#### Bullet point upgrades")
        for b in bullets:
            b = _dict(b)
            with st.container(border=True):
                st.markdown(f"**Before:** {b.get('original', '')}")
                st.markdown(f"**After:** {b.get('improved', '')}")
                if b.get("why"):
                    st.caption(b["why"])

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Keywords to add")
        for k in data.get("keywords_to_add") or ["None found"]:
            st.markdown(f"- {k}")
    with c2:
        st.markdown("#### Skills gap")
        for k in data.get("skills_gap") or ["None found"]:
            st.markdown(f"- {k}")

    if "rw_text" in ss:
        st.markdown("#### Tailored resume (you can edit it)")
        st.warning("Check every line before you send it. Replace any "
                   "[add metric] placeholder with a real number.")
        text = st.text_area("Tailored resume", key="rw_text", height=420,
                            label_visibility="collapsed")
        d1, d2 = st.columns(2)
        d1.download_button("⬇️ Download .txt", text,
                           file_name="tailored_resume.txt", key="rw_dl_txt")
        d2.download_button("⬇️ Download PDF", text_to_pdf("Resume", text),
                           file_name="tailored_resume.pdf",
                           mime="application/pdf", key="rw_dl_pdf")


# ============================================================== cover letter
def _cover_tab(resume, role, company, jd, name):
    ss = st.session_state
    c1, c2, c3 = st.columns(3)
    manager = c1.text_input("Hiring manager (optional)", key="cl_mgr")
    tone = c2.selectbox("Tone", ["Professional", "Friendly", "Confident"], key="cl_tone")
    length = c3.selectbox("Length", ["Short (about 150 words)",
                                     "Standard (about 250 words)"],
                          index=1, key="cl_len")

    if st.button("✉️ Write cover letter", type="primary", key="cl_btn"):
        if not resume:
            st.warning("Upload your resume in 'Your details' first.")
        elif not (role or company or jd):
            st.warning("Add a role, company or job description in 'Your details'.")
        else:
            try:
                with st.spinner("Writing your cover letter..."):
                    ss.cl_text = _ask(cover_letter_prompt(
                        resume, role, company, jd, name, manager.strip(), tone, length))
            except Exception as e:
                _fail(e)

    if "cl_text" in ss:
        st.warning("Read it carefully and make sure every claim is true before sending.")
        text = st.text_area("Cover letter", key="cl_text", height=380,
                            label_visibility="collapsed")
        d1, d2 = st.columns(2)
        d1.download_button("⬇️ Download .txt", text,
                           file_name="cover_letter.txt", key="cl_dl_txt")
        d2.download_button("⬇️ Download PDF", text_to_pdf("Cover Letter", text),
                           file_name="cover_letter.pdf",
                           mime="application/pdf", key="cl_dl_pdf")


# ====================================================== salary negotiation
def _negotiation_tab(role, company):
    ss = st.session_state
    neg = ss.get("neg")

    if not neg:
        st.caption("Practice with an AI recruiter who negotiates back. "
                   "It is a practice tool, not salary advice.")
        c1, c2, c3 = st.columns(3)
        unit = c1.text_input("Currency / unit", value="INR LPA", key="neg_unit")
        offer = c2.number_input("Recruiter's first offer", min_value=0.1,
                                value=10.0, step=0.5, key="neg_offer")
        target = c3.number_input("Your target", min_value=0.1,
                                 value=12.0, step=0.5, key="neg_target")
        level = st.select_slider("Recruiter style", ["Flexible", "Realistic", "Tough"],
                                 value="Realistic", key="neg_level")

        if st.button("🤝 Start negotiation", type="primary", key="neg_start"):
            if not role:
                st.warning("Add a target role in 'Your details' first.")
            else:
                opening = (
                    f"Hi! Thanks for your time today. We would like to offer you the "
                    f"{role} position"
                    f"{' at ' + company if company else ''} with a package of "
                    f"{offer:g} {unit}. How does that sound to you?"
                )
                ss.neg = {
                    "history": [{"role": "assistant", "content": opening}],
                    "role": role, "company": company, "unit": unit.strip() or "units",
                    "offer": offer, "target": target, "level": level,
                    "ceiling": recruiter_ceiling(offer, level),
                    "feedback": None, "saved": False,
                }
                st.rerun()
        return

    users = sum(1 for m in neg["history"] if m["role"] == "user")
    st.progress(min(users / MAX_TURNS, 1.0),
                text=f"Your replies: {users} of {MAX_TURNS}")
    for m in neg["history"]:
        with st.chat_message(m["role"]):
            st.write(m["content"])

    # ----- feedback view
    fb = neg["feedback"]
    if fb:
        score = fb["score"]
        (st.success if score >= 7 else st.warning if score >= 4 else st.error)(
            f"Negotiation score: {score} / 10")
        st.markdown(f"**Outcome:** {fb.get('outcome', '-')}")
        st.caption(f"The recruiter could have gone up to "
                   f"{neg['ceiling']:g} {neg['unit']}.")
        for title, key in (("✅ What went well", "went_well"),
                           ("⚠️ Mistakes", "mistakes"),
                           ("💬 Stronger phrases to use", "better_phrases"),
                           ("💡 Tips", "tips")):
            items = fb.get(key) or []
            if items:
                st.markdown(f"**{title}**")
                for it in items:
                    st.markdown(f"- {it}")

        if not neg["saved"]:
            details = [{
                "question": f"Salary negotiation: offer {neg['offer']:g}, "
                            f"target {neg['target']:g} {neg['unit']}",
                "score": score,
                "missing_points": "; ".join(fb.get("mistakes") or [])[:500] or "-",
            }]
            neg["saved"] = _save(neg["role"], "Negotiation", score, 10, details)
        if neg["saved"]:
            st.caption("✅ Saved to your progress history")

        if st.button("🔄 New negotiation", key="neg_new"):
            ss.pop("neg", None)
            st.rerun()
        return

    # ----- conversation view
    if users < MAX_TURNS:
        with st.form("neg_form", clear_on_submit=True):
            msg = st.text_area("Your reply", height=90,
                               placeholder="Explain your value and make your counter...")
            sent = st.form_submit_button("Send ➤")
        if sent and msg.strip():
            neg["history"].append({"role": "user", "content": msg.strip()[:1500]})
            try:
                with st.spinner("The recruiter is replying..."):
                    reply = _ask(recruiter_prompt(neg, last_round=(users + 1 >= MAX_TURNS)))
                neg["history"].append({"role": "assistant", "content": reply})
                st.rerun()
            except Exception as e:
                neg["history"].pop()  # undo so you can send it again
                _fail(e)
    else:
        st.info("You reached the round limit. Get your feedback below.")

    if st.button("🏁 End and get feedback", disabled=users == 0, key="neg_end"):
        try:
            with st.spinner("Reviewing your negotiation..."):
                result = _dict(_ask_json(negotiation_feedback_prompt(neg)))
            result["score"] = max(0, min(10, int(result.get("score", 0))))
            neg["feedback"] = result
            st.rerun()
        except Exception as e:
            _fail(e)


# ================================================================ quiz round
def _quiz_tab(resume, role):
    ss = st.session_state
    quiz = ss.get("quiz")

    if not quiz:
        kind = st.selectbox(
            "Quiz type",
            ["Technical (from my resume skills)", "Aptitude (quant, logical, verbal)",
             "Custom topic"], key="qz_kind")
        topic = ""
        if kind == "Custom topic":
            topic = st.text_input("Topic", key="qz_topic", placeholder="e.g. SQL joins")
        c1, c2 = st.columns(2)
        n = c1.slider("Questions", 5, 15, 8, key="qz_n")
        level = c2.selectbox("Difficulty", ["Easy", "Medium", "Hard"],
                             index=1, key="qz_level")
        st.caption("AI-written questions can occasionally have a wrong answer key. "
                   "Read the explanations.")

        if st.button("🧠 Generate quiz", type="primary", key="qz_btn"):
            if kind.startswith("Technical") and not resume:
                st.warning("Upload your resume in 'Your details' first.")
            elif kind == "Custom topic" and not topic.strip():
                st.warning("Enter a topic.")
            else:
                try:
                    with st.spinner("Writing questions..."):
                        raw = _ask_json(quiz_prompt(kind, topic.strip(), resume, role, n, level))
                    questions = normalize_quiz(raw, n)
                except Exception as e:
                    _fail(e)
                    return
                if len(questions) < 3:
                    st.error("Could not build a valid quiz. Please try again.")
                else:
                    ss.quiz = {"id": random.randint(1, 10**9), "questions": questions,
                               "kind": kind, "result": None, "saved": False}
                    st.rerun()
        return

    qs = quiz["questions"]

    # ----- taking the quiz
    if quiz["result"] is None:
        with st.form("quiz_form"):
            for i, q in enumerate(qs):
                st.markdown(f"**Q{i + 1}. {q['question']}**")
                st.radio("Choose one", q["options"], index=None,
                         key=f"qz_{quiz['id']}_{i}", label_visibility="collapsed")
            done = st.form_submit_button("✅ Submit quiz", type="primary")
        if done:
            answers = [ss.get(f"qz_{quiz['id']}_{i}") for i in range(len(qs))]
            correct = sum(1 for q, a in zip(qs, answers)
                          if a == q["options"][q["answer_index"]])
            quiz["result"] = {"answers": answers, "correct": correct}
            st.rerun()
        return

    # ----- results
    res = quiz["result"]
    total = len(qs)
    percent = res["correct"] / total * 100
    c1, c2, c3 = st.columns(3)
    c1.metric("Score", f"{res['correct']} / {total}")
    c2.metric("Percentage", f"{percent:.0f}%")
    c3.metric("Skipped", sum(1 for a in res["answers"] if a is None))

    if not quiz["saved"]:
        details = []
        for q, a in zip(qs, res["answers"]):
            right = q["options"][q["answer_index"]]
            ok = a == right
            details.append({"question": q["question"], "score": 10 if ok else 0,
                            "missing_points": "-" if ok else f"Correct answer: {right}"})
        quiz["saved"] = _save(role, "Quiz", res["correct"] * 10, total * 10, details)
    if quiz["saved"]:
        st.caption("✅ Saved to your progress history")

    for i, (q, a) in enumerate(zip(qs, res["answers"])):
        right = q["options"][q["answer_index"]]
        icon = "✅" if a == right else "❌"
        with st.expander(f"{icon} Q{i + 1}. {q['question']}"):
            st.markdown(f"**Your answer:** {a or 'Skipped'}")
            st.markdown(f"**Correct answer:** {right}")
            if q["explanation"]:
                st.markdown(f"**Why:** {q['explanation']}")

    if st.button("🔄 New quiz", key="qz_new"):
        ss.pop("quiz", None)
        st.rerun()


# =================================================================== page
def toolkit_page():
    st.title("🧰 Career Toolkit")
    resume = _details_block()
    ss = st.session_state
    role = (ss.get("tk_role") or "").strip()
    company = (ss.get("tk_company") or "").strip()
    name = (ss.get("tk_name") or "").strip()
    jd = (ss.get("tk_jd") or "").strip()[:6000]
    resume = resume[:12000]

    t1, t2, t3, t4 = st.tabs(["📝 Resume Rewriter", "✉️ Cover Letter",
                              "💰 Salary Negotiation", "🧠 Quiz Round"])
    with t1:
        _rewriter_tab(resume, role, jd)
    with t2:
        _cover_tab(resume, role, company, jd, name)
    with t3:
        _negotiation_tab(role, company)
    with t4:
        _quiz_tab(resume, role)