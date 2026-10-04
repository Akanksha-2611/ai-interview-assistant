import os
import re
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from pypdf import PdfReader

load_dotenv()

llm = ChatGoogleGenerativeAI(
    model="gemini-flash-lite-latest",
    google_api_key=os.getenv("GEMINI_API_KEY"),
    temperature=0,
)


def extract_resume_text(file):
    reader = PdfReader(file)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def generate_questions(resume_text):
    prompt = f"""
    You are a Senior Technical Interviewer.
    Analyze the resume and identify the candidate's skills.
    Generate 20 interview questions based on those skills.
    Include:
    - Technical Questions
    - Project-Based Questions
    - Scenario-Based Questions

    Resume:
    {resume_text}
    """
    return llm.invoke(prompt).text


def evaluate_answer(question, answer):
    prompt = f"""
    You are a technical interviewer.

    Question: {question}
    Candidate Answer: {answer}

    Evaluate:
    1. Score out of 10 (write it exactly like: Score: 7/10)
    2. Strengths
    3. Missing Points
    4. Correct Answer
    """
    return llm.invoke(prompt).text


def followup_question(question, answer):
    prompt = f"""
    Original Question: {question}
    Candidate Answer: {answer}
    Generate one follow-up question.
    """
    return llm.invoke(prompt).text


def extract_score(feedback):
    match = re.search(r"(\d+)\s*/\s*10", feedback)
    return int(match.group(1)) if match else None