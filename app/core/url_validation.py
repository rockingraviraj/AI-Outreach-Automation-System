from urllib.parse import urlsplit


def validate_http_url(value: str | None) -> str | None:
    """
    Accept only valid HTTP/HTTPS destination URLs.
    Reject empty values, unsafe schemes and embedded credentials.
    """

    if value is None:
        return None

    value = value.strip()

    if not value:
        raise ValueError(
            "Destination URL cannot be empty. Use null to remove it."
        )

    if any(character.isspace() for character in value):
        raise ValueError("Destination URL cannot contain whitespace")

    try:
        parsed = urlsplit(value)

        # Validate port syntax and range.
        parsed.port

    except ValueError as exc:
        raise ValueError("Invalid destination URL") from exc

    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Only HTTP and HTTPS URLs are allowed")

    if not parsed.hostname:
        raise ValueError("Destination URL must contain a hostname")

    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URLs containing credentials are not allowed")

    return value
