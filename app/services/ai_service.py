from openai import OpenAI

from app.core.config import settings


def generate_email(name: str, company: str):
    """
    Generate a personalized outreach email with a safe fallback.
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