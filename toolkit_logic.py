"""Logic for the Career Toolkit that does not touch Streamlit or the network."""
import random
import re

# ---------------------------------------------------------------- PDF export
_REPLACEMENTS = {
    "•": "-", "–": "-", "—": "-", "“": '"', "”": '"',
    "‘": "'", "’": "'", "…": "...", "\u00a0": " ", "₹": "Rs. ",
}


def pdf_safe(text):
    """fpdf's built-in fonts only support latin-1, so swap or drop the rest."""
    text = str(text).replace("**", "")
    for old, new in _REPLACEMENTS.items():
        text = text.replace(old, new)
    return text.encode("latin-1", "replace").decode("latin-1")


def text_to_pdf(title, body):
    from fpdf import FPDF  # imported here so the rest of this file needs no extras

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 8, pdf_safe(title), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 11)
    for line in str(body).split("\n"):
        pdf.multi_cell(0, 6, pdf_safe(line) or " ", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


# ------------------------------------------------------------------- Prompts
HONESTY_RULES = """
STRICT RULES:
- Use ONLY facts that appear in the resume. Never invent employers, job titles,
  dates, degrees, tools, numbers or achievements.
- If a number would strengthen a statement but the resume does not give one,
  write [add metric] instead of making one up.
- Start bullets with strong action verbs and keep each under 25 words.
"""


def rewrite_analysis_prompt(resume, role, jd):
    return f"""
You are an expert resume writer and recruiter.
Target role: {role or "Not specified"}
Job description: {jd or "Not provided"}

Resume:
{resume}

Improve this resume's wording and tailor it to the target role.
{HONESTY_RULES}
Return ONLY a JSON object, with no extra text:
{{
  "summary": "<2 to 3 sentence professional summary>",
  "bullets": [
    {{"original": "<bullet from the resume>", "improved": "<stronger version>", "why": "<short reason>"}}
  ],
  "keywords_to_add": ["<job keyword the candidate really has experience with but the resume does not mention>"],
  "skills_gap": ["<job requirement with no evidence in the resume>"]
}}
Give 5 to 8 bullets, choosing the weakest ones.
"""


def rewrite_resume_prompt(resume, role, jd):
    return f"""
You are an expert resume writer.
Target role: {role or "Not specified"}
Job description: {jd or "Not provided"}

Resume:
{resume}

Write the complete tailored resume as clean plain text, ready to paste into a document.
{HONESTY_RULES}
Sections, in this order (skip any that do not apply): NAME AND CONTACT, SUMMARY,
SKILLS, EXPERIENCE, PROJECTS, EDUCATION, CERTIFICATIONS.
Use simple headings in CAPITAL LETTERS and "- " for bullets. No markdown symbols
such as ** or #. Put nothing before or after the resume.
"""


def cover_letter_prompt(resume, role, company, jd, name, manager, tone, length):
    words = "about 150 words" if length.startswith("Short") else "about 250 words"
    greeting = manager or "Hiring Manager"
    return f"""
Write a cover letter.
Candidate name: {name or "[Your Name]"}
Role: {role or "the advertised role"}
Company: {company or "the company"}
Tone: {tone}
Length: {words}
Job description: {jd or "Not provided"}

Candidate resume:
{resume}

RULES:
- Use ONLY facts that appear in the resume. Never invent achievements, numbers or experience.
- Do not claim to know anything about the company beyond what the job description says.
- Start with "Dear {greeting}," then write 3 short paragraphs: why this role and company,
  two or three specific strengths from the resume matched to the job, and a polite closing
  with a call to action. Sign off with the candidate's name.
- Avoid cliches such as "I am writing to express my interest" and "team player".
- Plain text only, no markdown.
"""


def quiz_prompt(kind, topic, resume, role, n, level):
    if kind.startswith("Technical"):
        subject = (f"the technical skills found in this resume "
                   f"(target role: {role or 'General'}):\n{resume}")
    elif kind.startswith("Aptitude"):
        subject = ("aptitude: quantitative reasoning, logical reasoning and verbal "
                   "ability, mixed evenly")
    else:
        subject = f"the topic: {topic}"
    return f"""
You are an expert exam setter. Create {n} multiple-choice questions at {level}
difficulty about {subject}

RULES:
- Each question has exactly 4 options and exactly one correct answer.
- Options are plain text without A/B/C/D prefixes.
- For calculations, work the answer out step by step in the explanation and double-check it.
- Do not repeat questions.

Return ONLY a JSON array, with no extra text. Write the explanation BEFORE answer_index:
[{{"question": "...", "options": ["...", "...", "...", "..."], "explanation": "...", "answer_index": 0}}]
"""


# ------------------------------------------------------------------ Quiz data
_PREFIX = re.compile(r"^\(?[A-Da-d][\).:\-]\s+")


def normalize_quiz(raw, limit):
    """Validate the model's quiz JSON and shuffle options so the answer
    position is random. Bad questions are dropped, not guessed at."""
    if isinstance(raw, dict):
        raw = raw.get("questions", [])
    if not isinstance(raw, list):
        return []

    out = []
    for item in raw:
        try:
            question = str(item["question"]).strip()
            options = [_PREFIX.sub("", str(o).strip()) for o in item["options"]]
            answer = int(item["answer_index"])
        except (KeyError, TypeError, ValueError):
            continue
        if (not question or len(options) != 4 or not all(options)
                or len(set(options)) != 4 or not 0 <= answer < 4):
            continue
        correct = options[answer]
        random.shuffle(options)
        out.append({
            "question": question,
            "options": options,
            "answer_index": options.index(correct),
            "explanation": str(item.get("explanation", "")).strip(),
        })
    return out[:limit]


# ----------------------------------------------------------- Negotiation data
CEILING_FACTOR = {"Flexible": 1.20, "Realistic": 1.10, "Tough": 1.05}


def recruiter_ceiling(offer, level):
    """The most the simulated recruiter can go up to (hidden from the user)."""
    return round(float(offer) * CEILING_FACTOR.get(level, 1.10), 2)


def transcript_text(history):
    return "\n".join(
        f"{'Candidate' if m['role'] == 'user' else 'Recruiter'}: {m['content']}"
        for m in history
    )


def recruiter_prompt(neg, last_round=False):
    closing = ("This is the final round: state your final offer clearly "
               "and close politely." if last_round else "")
    return f"""
You are a recruiter at {neg['company'] or 'a company'} negotiating a job offer
for the role of {neg['role']}.
Your first offer was {neg['offer']} {neg['unit']}.
Your hidden maximum is {neg['ceiling']} {neg['unit']}. Never reveal it and never offer more.
Behave realistically: stay polite, push back on weak or vague arguments, and move up
in small steps only when the candidate gives strong reasons (market data, skills,
impact, competing offers). If you cannot raise the salary, offer non-salary options
such as a joining bonus, an earlier review, remote days or a learning budget.
{closing}
Reply as the recruiter in 2 to 4 sentences. Plain text, no markdown.

Conversation so far:
{transcript_text(neg['history'])}

Recruiter:"""


def negotiation_feedback_prompt(neg):
    return f"""
You are a career coach reviewing a salary negotiation practice session.
Role: {neg['role']}
First offer: {neg['offer']} {neg['unit']}
Candidate's target: {neg['target']} {neg['unit']}
The recruiter could have gone up to {neg['ceiling']} {neg['unit']} (the candidate did not know this).

Transcript:
{transcript_text(neg['history'])}

Score the candidate from 0 to 10 on preparation, justifying the ask with concrete
value, tone, use of non-salary options, and not accepting too early.
Return ONLY a JSON object, with no extra text:
{{
  "score": <integer 0 to 10>,
  "outcome": "<what was agreed, or 'no agreement'>",
  "went_well": ["..."],
  "mistakes": ["..."],
  "better_phrases": ["<a stronger sentence the candidate could have said>"],
  "tips": ["..."]
}}
"""