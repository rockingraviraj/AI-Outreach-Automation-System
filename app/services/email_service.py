import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings


def send_email(
    to_email: str,
    subject: str,
    body: str
) -> bool:

    if not settings.SMTP_EMAIL:
        raise RuntimeError(
            "SMTP_EMAIL is not configured"
        )

    if not settings.SMTP_PASSWORD:
        raise RuntimeError(
            "SMTP_PASSWORD is not configured"
        )

    message = MIMEMultipart("alternative")

    message["From"] = settings.SMTP_EMAIL
    message["To"] = to_email
    message["Subject"] = subject

    message.attach(
        MIMEText(
            body,
            "html",
            "utf-8"
        )
    )

    server = None

    try:
        server = smtplib.SMTP(
            settings.SMTP_SERVER,
            settings.SMTP_PORT,
            timeout=30
        )

        server.starttls()

        server.login(
            settings.SMTP_EMAIL,
            settings.SMTP_PASSWORD
        )

        server.send_message(message)

        return True

    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass