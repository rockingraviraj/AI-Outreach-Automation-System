
import logging
import re

from openai import OpenAI

from app.core.config import settings


logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


def _get_ai_client() -> OpenAI:
    """Create an OpenAI-compatible client configured for Groq."""

    if not settings.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not configured")

    return OpenAI(
        api_key=settings.GROQ_API_KEY,
        base_url=GROQ_BASE_URL,
        timeout=45.0,
    )


def _generate_content(prompt: str, max_tokens: int = 1024) -> str:
    """Generate text using the configured Groq model."""

    client = _get_ai_client()

    response = client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        max_completion_tokens=max_tokens,
        temperature=0.7,
        extra_body={
            "reasoning_effort": "low"
        },
    )

    content = response.choices[0].message.content

    if not content or not content.strip():
        raise RuntimeError("Empty Groq AI response")

    return content.strip()


def clean_email_body(content: str) -> str:
    """
    Remove placeholders and incomplete sender signatures
    from generated email content.
    """

    cleaned_lines = []

    placeholder_pattern = re.compile(
        r"^\s*(?:"
        r"\[[^\]]+\]"
        r"|your\s+(?:name|company|title|position|email|phone)"
        r"|contact\s+information"
        r")\s*$",
        re.IGNORECASE,
    )

    for line in content.splitlines():

        line = re.sub(
            r"\s*\[(?:your name|your company|your title|contact information)\]",
            "",
            line,
            flags=re.IGNORECASE,
        )

        if placeholder_pattern.match(line):
            continue

        cleaned_lines.append(line.rstrip())

    # Remove incomplete closing signatures.
    closing_pattern = re.compile(
        r"^\s*(?:"
        r"best"
        r"|best regards"
        r"|kind regards"
        r"|warm regards"
        r"|regards"
        r"|sincerely"
        r")\s*[,!.]?\s*$",
        re.IGNORECASE,
    )

    while cleaned_lines and not cleaned_lines[-1].strip():
        cleaned_lines.pop()

    while cleaned_lines and closing_pattern.match(cleaned_lines[-1]):
        cleaned_lines.pop()

        while cleaned_lines and not cleaned_lines[-1].strip():
            cleaned_lines.pop()

    result = "\n".join(cleaned_lines)

    # Normalize excessive blank lines.
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result.strip()


def _email_requirements() -> str:
    """Strict factual rules for outreach email generation."""

    return """
Requirements:
- Write a professional, natural and concise first-contact email.
- Keep the email body under 100 words.
- Use only the recipient name and company provided in the input.
- Never claim you researched, followed, or know the recipient's work.
- Never invent the company's industry, projects, products,
  achievements, technology stack, or business challenges.
- Never invent statistics, percentages, client results, or case studies.
- Never claim sender experience, services, credentials, or achievements
  unless explicitly provided.
- Do not make guarantees or unsupported business claims.
- Do not include fake names, company names, titles, or contact details.
- Never include placeholders such as [Your Name] or [Your Company].
- Do not append a sender signature.
- When information is limited, write a neutral introduction
  and politely ask whether the recipient is open to connecting.
- Return only the requested email content.
"""


def generate_email(name: str, company: str) -> str:
    """
    Generate a personalized outreach email.

    Return type remains string for compatibility with
    the existing Celery worker and email-sending flow.
    """

    try:
        prompt = f"""
You are an expert professional sales copywriter.

Write a short, personalized cold outreach email.

Recipient name: {name}
Company: {company}

{_email_requirements()}

Return only the email body.
"""

        content = _generate_content(
            prompt,
            max_tokens=1024,
        )

        content = clean_email_body(content)

        if not content:
            raise RuntimeError("Email body became empty after cleaning")

        return content

    except Exception as exc:
        logger.exception("GROQ AI FALLBACK USED: %r", exc)

        fallback = f"""
Hi {name},

I’m reaching out to introduce myself and explore whether there may be an opportunity to connect with {company}.

Would you be open to a brief conversation?

Thank you.
"""

        return clean_email_body(fallback)


def generate_email_preview(name: str, company: str):
    """
    Generate a structured AI email preview.

    Response format remains:
    subject, body, source.
    """

    try:
        prompt = f"""
You are an expert professional sales copywriter.

Generate a concise, personalized cold outreach email.

Recipient name: {name}
Company: {company}

{_email_requirements()}

Return exactly this format:

SUBJECT: Your email subject
BODY: Your email body
"""

        content = _generate_content(
            prompt,
            max_tokens=1024,
        )

        lines = [
            line.strip()
            for line in content.splitlines()
            if line.strip()
        ]

        subject = None
        body_lines = []
        reading_body = False

        for line in lines:

            if line.lower().startswith("subject:"):
                subject = line.split(":", 1)[1].strip()
                reading_body = False

            elif line.lower().startswith("body:"):
                body_text = line.split(":", 1)[1].strip()

                if body_text:
                    body_lines.append(body_text)

                reading_body = True

            elif reading_body:
                body_lines.append(line)

        if not subject:
            raise RuntimeError("AI response subject is missing")

        subject = clean_email_body(subject)

        body = clean_email_body(
            "\n".join(body_lines)
        )

        if not subject:
            raise RuntimeError("AI response subject is empty")

        if not body:
            raise RuntimeError("AI response body is missing")

        return {
            "subject": subject,
            "body": body,
            "source": "ai",
        }

    except Exception as exc:
        logger.exception(
            "GROQ AI PREVIEW FALLBACK USED: %r",
            exc,
        )

        return {
            "subject": "Exploring a potential collaboration",
            "body": clean_email_body(
                f"""
Hi {name},

I’m reaching out to introduce myself and explore whether there may be an opportunity to connect with {company}.

Would you be open to a brief conversation?

Thank you.
"""
            ),
            "source": "fallback",
        }
