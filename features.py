import io
import re
import json
import wave
import base64
import random
from PIL import Image, ImageDraw, ImageFont
from langchain_core.messages import HumanMessage
from llm_utils import llm


def _loose_json(text):
    """Parse JSON from the model, tolerating code fences and raw newlines."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    return json.loads(text, strict=False)


# ====================== COMPANY RESEARCH ======================
def research_company(company, role=""):
    prompt = f"""
    You are a career coach. Write an interview-prep brief about the company
    "{company}" for the role "{role or 'General'}".
    Use current information from the web if you can. If you are not sure
    about a fact, say so instead of guessing.

    Cover briefly:
    - What the company does
    - Products and tech stack (if known)
    - Culture and values
    - Typical interview style
    - 5 topics the candidate should prepare

    Keep it under 250 words.
    """
    try:
        searching = llm.bind_tools([{"google_search": {}}])
        text = searching.invoke(prompt).text
        if text and text.strip():
            return text.strip()
    except Exception:
        pass
    try:
        return llm.invoke(prompt).text.strip()
    except Exception:
        return ""


# ====================== CODING ROUND ======================
def generate_coding_problem(difficulty, language, role="", asked=None):
    asked_text = ", ".join(asked or []) or "none"
    prompt = f"""
    You are a technical interviewer. Create ONE {difficulty} coding interview
    problem that can be solved in {language}.
    Role: {role or 'General software engineer'}.
    Do not repeat these problems: {asked_text}.
    Variety seed: {random.randint(1, 10**6)}

    Return ONLY a JSON object, with no extra text:
    {{
      "title": "...",
      "statement": "...",
      "example": "sample input and expected output",
      "constraints": "...",
      "hint": "..."
    }}
    """
    try:
        return _loose_json(llm.invoke(prompt).text)
    except Exception:
        return None


def review_code(problem, code, language):
    prompt = f"""
    You are a senior engineer doing a code review in an interview.
    You cannot run the code, so reason about it carefully.

    Problem: {problem['title']}
    {problem['statement']}

    Candidate's {language} solution:
    {code}

    Return ONLY a JSON object, with no extra text:
    {{
      "score": <integer 0 to 10>,
      "verdict": "<one sentence>",
      "correctness": "<does it solve the problem, including edge cases?>",
      "time_complexity": "<Big-O with a short reason>",
      "space_complexity": "<Big-O with a short reason>",
      "bugs": ["..."],
      "improvements": ["..."],
      "better_solution": "<clean, correct {language} solution>"
    }}
    """
    try:
        r = _loose_json(llm.invoke(prompt).text)
        r["score"] = max(0, min(10, int(r.get("score", 0))))
        return r
    except Exception:
        return None


# ====================== SPEAKING PRACTICE ======================
FILLER_PATTERNS = {
    "um": r"\bum+\b",
    "uh": r"\buh+\b",
    "er": r"\ber+\b",
    "ah": r"\bah+\b",
    "like": r"\blike\b",
    "you know": r"\byou know\b",
    "i mean": r"\bi mean\b",
    "basically": r"\bbasically\b",
    "actually": r"\bactually\b",
    "literally": r"\bliterally\b",
    "sort of": r"\bsort of\b",
    "kind of": r"\bkind of\b",
}


def transcribe_verbatim(audio_bytes):
    b64 = base64.b64encode(audio_bytes).decode()
    message = HumanMessage(
        content=[
            {"type": "text",
             "text": "Transcribe this audio word for word, exactly as spoken. "
                     "Keep every filler word (um, uh, like, you know, I mean) "
                     "and repeated words. Do not clean up or correct anything. "
                     "Return only the transcript."},
            {"type": "media", "mime_type": "audio/wav", "data": b64},
        ]
    )
    return llm.invoke([message]).text.strip()


def audio_duration(audio_bytes):
    """Length of a WAV recording in seconds (0 if it can't be read)."""
    try:
        with wave.open(io.BytesIO(audio_bytes)) as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 0.0


def count_fillers(text):
    t = text.lower()
    counts = {}
    for name, pattern in FILLER_PATTERNS.items():
        n = len(re.findall(pattern, t))
        if n:
            counts[name] = n
    return counts


def analyze_speech(question, transcript, wpm, filler_total):
    prompt = f"""
    You are a speaking coach for job interviews.

    Question: {question}
    Transcript of the spoken answer: {transcript}
    Speaking pace: {wpm} words per minute. Filler words detected: {filler_total}.

    Return ONLY a JSON object, with no extra text:
    {{
      "clarity": <integer 0 to 10>,
      "structure": <integer 0 to 10>,
      "confidence": <integer 0 to 10>,
      "summary": "<2 sentences>",
      "tips": ["<specific tip>", "<specific tip>", "<specific tip>"]
    }}
    """
    try:
        return _loose_json(llm.invoke(prompt).text)
    except Exception:
        return None


# ====================== SCORE CARD ======================
def _font(size):
    for name in ("arial.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _ascii(text):
    return str(text).encode("ascii", "replace").decode()


def make_score_card(name, percent, total, max_score, mode, role=""):
    W, H = 1080, 566
    img = Image.new("RGB", (W, H), (15, 23, 42))
    d = ImageDraw.Draw(img)

    if percent >= 85:
        label, color = "Outstanding", (34, 197, 94)
    elif percent >= 70:
        label, color = "Strong performance", (34, 197, 94)
    elif percent >= 50:
        label, color = "Good progress", (245, 158, 11)
    else:
        label, color = "Keep practicing", (239, 68, 68)

    d.rectangle([0, 0, W, 12], fill=(255, 75, 75))
    d.text((60, 45), "AI Interview Assistant", font=_font(34), fill=(148, 163, 184))
    d.text((60, 105), _ascii(name)[:24], font=_font(54), fill=(255, 255, 255))
    sub = f"{mode} interview" + (f" | {role}" if role else "")
    d.text((60, 180), _ascii(sub)[:55], font=_font(30), fill=(148, 163, 184))

    d.text((60, 245), f"{percent:.0f}%", font=_font(150), fill=(255, 255, 255))
    d.text((470, 300), f"{total} / {max_score} points", font=_font(40), fill=(226, 232, 240))
    d.text((470, 365), label, font=_font(40), fill=color)

    d.rounded_rectangle([60, 470, 1020, 500], radius=15, fill=(51, 65, 85))
    fill_w = int(960 * percent / 100)
    if fill_w > 30:
        d.rounded_rectangle([60, 470, 60 + fill_w, 500], radius=15, fill=color)

    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()