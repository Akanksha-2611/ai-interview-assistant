import smtplib
import ssl
from email.message import EmailMessage
from db import _secret


def email_enabled():
    return bool(_secret("SMTP_USER") and _secret("SMTP_PASSWORD"))


def send_report(to_email, pdf_bytes, role, mode, percent):
    host = _secret("SMTP_HOST") or "smtp.gmail.com"
    port = int(_secret("SMTP_PORT") or 465)
    user = _secret("SMTP_USER")
    password = _secret("SMTP_PASSWORD")

    msg = EmailMessage()
    msg["Subject"] = f"Your {mode} interview report ({percent:.0f}%)"
    msg["From"] = user
    msg["To"] = to_email
    msg.set_content(
        f"Hi,\n\nYour AI interview report is attached.\n\n"
        f"Role: {role or 'General'}\nMode: {mode}\nScore: {percent:.0f}%\n\n"
        f"Keep practicing!\nAI Interview Assistant"
    )
    msg.add_attachment(
        pdf_bytes, maintype="application", subtype="pdf",
        filename="interview_report.pdf",
    )

    with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context()) as s:
        s.login(user, password)
        s.send_message(msg)