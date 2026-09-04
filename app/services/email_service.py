import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv

load_dotenv()


SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")


def send_email(
    to_email: str,
    subject: str,
    body: str
) -> bool:

    if not SMTP_EMAIL:
        raise RuntimeError("SMTP_EMAIL is not configured")

    if not SMTP_PASSWORD:
        raise RuntimeError("SMTP_PASSWORD is not configured")

    message = MIMEMultipart("alternative")

    message["From"] = SMTP_EMAIL
    message["To"] = to_email
    message["Subject"] = subject

    message.attach(
        MIMEText(body, "html", "utf-8")
    )

    server = None

    try:
        server = smtplib.SMTP(
            SMTP_SERVER,
            SMTP_PORT,
            timeout=30
        )

        server.starttls()

        server.login(
            SMTP_EMAIL,
            SMTP_PASSWORD
        )

        server.send_message(message)

        return True

    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass