import os
import re
import json
import base64
import streamlit as st
from dotenv import load_dotenv
from fpdf import FPDF
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pypdf import PdfReader

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        api_key = None

llm = ChatGoogleGenerativeAI(
    model="gemini-flash-lite-latest",
    google_api_key=api_key,
    temperature=0,
)

LEVELS = ["Easy", "Medium", "Hard"]


def _parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    return json.loads(text)


def extract_resume_text(file):
    reader = PdfReader(file)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def adjust_difficulty(current, last_score):
    """Raise difficulty after a strong answer, lower it after a weak one."""
    if last_score is None:
        return current
    i = LEVELS.index(current)
    if last_score >= 8:
        i = min(i + 1, len(LEVELS) - 1)
    elif last_score <= 4:
        i = max(i - 1, 0)
    return LEVELS[i]


def generate_next_question(resume_text, job_desc, role, difficulty, q_type, asked):
    asked_text = "\n".join(f"- {q}" for q in asked) or "None yet"
    prompt = f"""
    You are a Senior Technical Interviewer interviewing for the role: {role or "General"}.

    Job description (may be empty):
    {job_desc or "Not provided"}

    Candidate resume:
    {resume_text}

    Ask ONE new {q_type} interview question at {difficulty} difficulty.
    It must fit the candidate's skills and the role.
    Do NOT repeat or closely resemble these earlier questions:
    {asked_text}

    Return ONLY a JSON object, with no extra text:
    {{"type": "{q_type}", "question": "..."}}
    """
    try:
        q = _parse_json(llm.invoke(prompt).text)
        q["difficulty"] = difficulty
        q.setdefault("type", q_type)
        return q
    except Exception:
        return None


def evaluate_answer(question, answer, role="", job_desc=""):
    prompt = f"""
    You are a strict but fair technical interviewer hiring for: {role or "General"}.
    Job description: {job_desc or "Not provided"}

    Question: {question}
    Candidate Answer: {answer}

    Evaluate the answer and return ONLY a JSON object, with no extra text:
    {{
      "score": <integer from 0 to 10>,
      "strengths": "<short text>",
      "missing_points": "<short text>",
      "ideal_answer": "<concise correct answer>"
    }}
    """
    try:
        result = _parse_json(llm.invoke(prompt).text)
        result["score"] = max(0, min(10, int(result.get("score", 0))))
        return result
    except Exception:
        return {
            "score": 0,
            "strengths": "Could not evaluate this answer.",
            "missing_points": "Please try again.",
            "ideal_answer": "",
        }


def followup_question(question, answer):
    prompt = f"""
    Original Question: {question}
    Candidate Answer: {answer}
    Generate one short follow-up question.
    """
    return llm.invoke(prompt).text


def transcribe_audio(audio_bytes):
    """Convert a recorded answer to text using Gemini."""
    b64 = base64.b64encode(audio_bytes).decode()
    message = HumanMessage(
        content=[
            {"type": "text",
             "text": "Transcribe this audio exactly. Return only the transcript."},
            {"type": "media", "mime_type": "audio/wav", "data": b64},
        ]
    )
    return llm.invoke([message]).text.strip()


def generate_final_report(results, role=""):
    summary = "\n".join(
        f"Q{i+1} ({r['type']}, {r['difficulty']}): {r['question']}\n"
        f"Score: {r['score']}/10, Time: {r['time_taken']}s"
        for i, r in enumerate(results)
    )
    prompt = f"""
    You are a senior interviewer writing a final report for the role: {role or "General"}.

    Interview results:
    {summary}

    Write a short report with these sections:
    1. Overall Performance
    2. Strong Areas
    3. Weak Areas
    4. Recommendations to Improve
    5. Hiring Verdict (Strong Hire / Hire / Borderline / No Hire)
    """
    return llm.invoke(prompt).text


def _clean(text):
    """fpdf's built-in fonts only support latin-1, so remove other characters."""
    text = str(text).replace("**", "").replace("#", "")
    return text.encode("latin-1", "replace").decode("latin-1")


def build_pdf(results, report, role, total_score, max_score):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    def write(text, size=11, bold=False):
        pdf.set_font("Helvetica", "B" if bold else "", size)
        pdf.multi_cell(0, 6, _clean(text), new_x="LMARGIN", new_y="NEXT")

    percent = total_score / max_score * 100 if max_score else 0
    write("AI Interview Report", 18, True)
    write(f"Role: {role or 'General'}")
    write(f"Total Score: {total_score}/{max_score} ({percent:.0f}%)", 12, True)
    pdf.ln(4)

    write("AI Feedback", 14, True)
    write(report)
    pdf.ln(4)

    write("Question-wise Breakdown", 14, True)
    for i, r in enumerate(results):
        pdf.ln(2)
        write(f"Q{i+1} [{r['type']} | {r['difficulty']}] Score: {r['score']}/10 "
              f"| Time: {r['time_taken']}s", 11, True)
        write(f"Question: {r['question']}")
        write(f"Your answer: {r['answer']}")
        write(f"Missing points: {r['missing_points']}")
        write(f"Ideal answer: {r['ideal_answer']}")

    return bytes(pdf.output())