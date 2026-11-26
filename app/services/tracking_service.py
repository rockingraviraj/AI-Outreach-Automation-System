
import html
from urllib.parse import quote

from app.core.config import settings


def build_tracked_email_body(
    ai_content: str,
    tracking_token: str,
    destination_url: str | None = None,
) -> str:
    """
    Build HTML email with:
    - Existing open tracking pixel
    - Optional tracked CTA link

    Original destination URL is stored in the Email database record.
    The email only exposes the tracking endpoint.
    """

    base_url = settings.APP_BASE_URL.rstrip("/")
    safe_token = quote(tracking_token, safe="")

    open_tracking_url = (
        f"{base_url}/tracking/open/{safe_token}"
    )

    click_tracking_url = (
        f"{base_url}/tracking/click/{safe_token}"
    )

    # AI output is plain text. Escape HTML and preserve line breaks.
    safe_content = html.escape(ai_content)
    safe_content = safe_content.replace("\r\n", "\n")
    safe_content = safe_content.replace("\r", "\n")
    safe_content = safe_content.replace("\n", "<br>\n")

    cta_html = ""

    if destination_url:
        safe_click_url = html.escape(
            click_tracking_url,
            quote=True,
        )

        cta_html = f"""
        <p>
            <a href="{safe_click_url}">
                Learn more
            </a>
        </p>
        """

    safe_open_url = html.escape(
        open_tracking_url,
        quote=True,
    )

    return f"""
    <html>
        <body>
            {safe_content}

            {cta_html}

            <img
                src="{safe_open_url}"
                width="1"
                height="1"
                alt=""
                style="display:none;"
            />
        </body>
    </html>
    """
