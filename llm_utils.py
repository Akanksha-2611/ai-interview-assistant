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

MODES = {
    "Technical": {
        "types": ["Technical", "Project-Based", "Scenario-Based"],
        "focus": "technical depth, correctness and practical experience",
    },
    "HR": {
        "types": ["Motivation", "Career Goals", "Culture Fit", "Situational"],
        "focus": "communication, motivation, self-awareness and culture fit",
    },
    "Behavioral": {
        "types": ["Teamwork", "Conflict", "Leadership", "Failure & Learning"],
        "focus": "use of the STAR method (Situation, Task, Action, Result) "
                 "with concrete real examples",
    },
    "System Design": {
        "types": ["Architecture", "Scalability", "Trade-offs"],
        "focus": "architecture choices, scalability, trade-offs and clear reasoning",
    },
}


def _parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    return json.loads(text)


def extract_resume_text(file):
    reader = PdfReader(file)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def adjust_difficulty(current, last_score):
    if last_score is None:
        return current
    i = LEVELS.index(current)
    if last_score >= 8:
        i = min(i + 1, len(LEVELS) - 1)
    elif last_score <= 4:
        i = max(i - 1, 0)
    return LEVELS[i]


def generate_next_question(resume_text, job_desc, role, difficulty,
                           q_type, asked, mode="Technical"):
    asked_text = "\n".join(f"- {q}" for q in asked) or "None yet"
    prompt = f"""
    You are a Senior Interviewer running a {mode} interview for the role: {role or "General"}.

    Job description (may be empty):
    {job_desc or "Not provided"}

    Candidate resume:
    {resume_text}

    Ask ONE new {q_type} question at {difficulty} difficulty.
    Focus on: {MODES[mode]["focus"]}.
    It must fit the candidate's background and the role.
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


def evaluate_answer(question, answer, role="", job_desc="", mode="Technical"):
    prompt = f"""
    You are a strict but fair interviewer running a {mode} interview
    for the role: {role or "General"}.
    Job description: {job_desc or "Not provided"}
    Judge mainly on: {MODES[mode]["focus"]}.

    Question: {question}
    Candidate Answer: {answer}

    Evaluate the answer and return ONLY a JSON object, with no extra text:
    {{
      "score": <integer from 0 to 10>,
      "strengths": "<short text>",
      "missing_points": "<short text>",
      "ideal_answer": "<concise strong sample answer>"
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
    b64 = base64.b64encode(audio_bytes).decode()
    message = HumanMessage(
        content=[
            {"type": "text",
             "text": "Transcribe this audio exactly. Return only the transcript."},
            {"type": "media", "mime_type": "audio/wav", "data": b64},
        ]
    )
    return llm.invoke([message]).text.strip()


def analyze_resume(resume_text, role="", job_desc=""):
    prompt = f"""
    You are an expert recruiter and ATS (applicant tracking system) specialist.
    Target role: {role or "General"}
    Job description: {job_desc or "Not provided"}

    Resume:
    {resume_text}

    Review the resume and return ONLY a JSON object, with no extra text:
    {{
      "ats_score": <integer 0 to 100>,
      "summary": "<2 sentence overall impression>",
      "strengths": ["...", "..."],
      "weaknesses": ["...", "..."],
      "missing_keywords": ["...", "..."],
      "suggestions": ["...", "..."]
    }}
    """
    try:
        data = _parse_json(llm.invoke(prompt).text)
        data["ats_score"] = max(0, min(100, int(data.get("ats_score", 0))))
        return data
    except Exception:
        return None


def generate_final_report(results, role="", mode="Technical"):
    summary = "\n".join(
        f"Q{i+1} ({r['type']}, {r['difficulty']}): {r['question']}\n"
        f"Score: {r['score']}/10, Time: {r['time_taken']}s"
        for i, r in enumerate(results)
    )
    prompt = f"""
    You are a senior interviewer writing a final report for a {mode} interview
    for the role: {role or "General"}.

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
    text = str(text).replace("**", "").replace("#", "")
    return text.encode("latin-1", "replace").decode("latin-1")


def build_pdf(results, report, role, mode, total_score, max_score):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    def write(text, size=11, bold=False):
        pdf.set_font("Helvetica", "B" if bold else "", size)
        pdf.multi_cell(0, 6, _clean(text), new_x="LMARGIN", new_y="NEXT")

    percent = total_score / max_score * 100 if max_score else 0
    write("AI Interview Report", 18, True)
    write(f"Role: {role or 'General'}   |   Mode: {mode}")
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