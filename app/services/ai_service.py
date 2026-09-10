from openai import OpenAI

from app.core.config import settings


def generate_email(name: str, company: str):
    """
    Generate a personalized outreach email with a safe fallback.

    This function is used by the existing email-sending flow
    and Celery worker. Keep its return type backward-compatible.
    """

    try:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured"
            )

        client = OpenAI(
            api_key=settings.OPENAI_API_KEY
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert sales copywriter."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Write a short, personalized cold email "
                        f"for {name} who works at {company}. "
                        "Keep it professional, engaging, "
                        "and under 100 words."
                    )
                }
            ],
            max_tokens=150,
            temperature=0.7
        )

        content = response.choices[0].message.content

        if not content:
            raise RuntimeError(
                "Empty AI response"
            )

        return content

    except Exception as exc:
        print(
            "AI FALLBACK USED:",
            repr(exc)
        )

        return f"""
Hi {name},

I came across your work at {company} and found it really impressive.

I'd love to connect and explore if there's any opportunity to collaborate or add value.

Looking forward to hearing from you.

Best regards,
Your Name
"""


def generate_email_preview(name: str, company: str):
    """
    Generate structured AI email preview content.

    This function is used only by the new AI preview endpoint.
    The existing generate_email() function remains unchanged for
    the email-sending and Celery flows.
    """

    try:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured"
            )

        client = OpenAI(
            api_key=settings.OPENAI_API_KEY
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert sales copywriter. "
                        "Generate a concise, professional cold outreach email. "
                        "Return the response exactly in this format:\n"
                        "SUBJECT: <subject>\n"
                        "BODY: <body>"
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Write a personalized cold email "
                        f"for {name} who works at {company}. "
                        "Keep the email professional and engaging. "
                        "Keep the body under 100 words."
                    )
                }
            ],
            max_tokens=180,
            temperature=0.7
        )

        content = response.choices[0].message.content

        if not content:
            raise RuntimeError(
                "Empty AI response"
            )

        lines = [
            line.strip()
            for line in content.splitlines()
            if line.strip()
        ]

        subject = None
        body_lines = []

        for line in lines:
            if line.lower().startswith("subject:"):
                subject = line.split(
                    ":",
                    1
                )[1].strip()

            elif line.lower().startswith("body:"):
                body_text = line.split(
                    ":",
                    1
                )[1].strip()

                if body_text:
                    body_lines.append(body_text)

            elif subject is not None:
                body_lines.append(line)

        body = "\n".join(body_lines).strip()

        if not subject:
            raise RuntimeError(
                "AI response subject is missing"
            )

        if not body:
            raise RuntimeError(
                "AI response body is missing"
            )

        return {
            "subject": subject,
            "body": body,
            "source": "ai"
        }

    except Exception as exc:
        print(
            "AI PREVIEW FALLBACK USED:",
            repr(exc)
        )

        return {
            "subject": "Exploring a potential collaboration",
            "body": (
                f"Hi {name},\n\n"
                f"I came across your work at {company} and found it "
                "really impressive.\n\n"
                "I'd love to connect and explore if there's any "
                "opportunity to collaborate or add value.\n\n"
                "Looking forward to hearing from you.\n\n"
                "Best regards,\n"
                "Your Name"
            ),
            "source": "fallback"
        }