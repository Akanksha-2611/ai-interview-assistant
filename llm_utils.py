import os
import re
import json
import streamlit as st
from dotenv import load_dotenv
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


def _parse_json(text):
    """Remove ```json fences and parse the JSON."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    return json.loads(text)


def extract_resume_text(file):
    reader = PdfReader(file)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def generate_question_list(resume_text, num_questions=5, difficulty="Medium"):
    prompt = f"""
    You are a Senior Technical Interviewer.
    Analyze the resume and identify the candidate's skills.
    Generate exactly {num_questions} interview questions at {difficulty} difficulty.
    Mix these types: Technical, Project-Based, Scenario-Based.
    Order them from easier to harder.

    Return ONLY a JSON array, with no extra text, like this:
    [
      {{"type": "Technical", "question": "..."}},
      {{"type": "Project-Based", "question": "..."}}
    ]

    Resume:
    {resume_text}
    """
    try:
        questions = _parse_json(llm.invoke(prompt).text)
        return questions[:num_questions]
    except Exception:
        return []


def evaluate_answer(question, answer):
    prompt = f"""
    You are a strict but fair technical interviewer.

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


def generate_final_report(results):
    summary = "\n".join(
        f"Q{i+1} ({r['type']}): {r['question']}\nScore: {r['score']}/10"
        for i, r in enumerate(results)
    )
    prompt = f"""
    You are a senior interviewer writing a final report.

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