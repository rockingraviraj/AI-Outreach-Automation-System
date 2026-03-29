from openai import OpenAI
import os


def generate_email(name: str, company: str):
    """
    AI email generation (safe + fallback + production ready)
    """

    try:
        # 🔐 Step 1: API key check
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise Exception("API key missing")

        # 🔥 Step 2: client create (lazy)
        client = OpenAI(api_key=api_key)

        # 🔥 Step 3: AI call
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert sales copywriter."
                },
                {
                    "role": "user",
                    "content": f"""
                    Write a short, personalized cold email for {name} who works at {company}.
                    Keep it professional, engaging, and under 100 words.
                    """
                }
            ],
            max_tokens=150,
            temperature=0.7
        )

        content = response.choices[0].message.content

        # ✅ safety check
        if not content:
            raise Exception("Empty AI response")

        return content

    except Exception as e:
        # ❌ ANY ERROR → fallback
        print("AI FALLBACK USED:", str(e))

        return f"""
Hi {name},

I came across your work at {company} and found it really impressive.

I’d love to connect and explore if there’s any opportunity to collaborate or add value.

Looking forward to hearing from you.

Best regards,  
Your Name
"""