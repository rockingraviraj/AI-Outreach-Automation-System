from pathlib import Path
import os

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[2]

load_dotenv(BASE_DIR / ".env")


class Settings:
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str

    SMTP_SERVER: str
    SMTP_PORT: int
    SMTP_EMAIL: str | None
    SMTP_PASSWORD: str | None

    REDIS_URL: str
    APP_BASE_URL: str
    OPENAI_API_KEY: str | None

    CORS_ORIGINS: list[str]
    FORCE_EMAIL_FAILURE: bool

    def __init__(self) -> None:
        self.DATABASE_URL = self._required("DATABASE_URL")

        self.SECRET_KEY = self._required("SECRET_KEY")
        if len(self.SECRET_KEY) < 32:
            raise RuntimeError(
                "SECRET_KEY must be at least 32 characters long"
            )

        self.ALGORITHM = os.getenv(
            "ALGORITHM",
            "HS256"
        )

        self.SMTP_SERVER = os.getenv(
            "SMTP_SERVER",
            "smtp.gmail.com"
        )

        try:
            self.SMTP_PORT = int(
                os.getenv("SMTP_PORT", "587")
            )
        except ValueError as exc:
            raise RuntimeError(
                "SMTP_PORT must be a valid integer"
            ) from exc

        self.SMTP_EMAIL = os.getenv("SMTP_EMAIL")
        self.SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

        self.REDIS_URL = self._required("REDIS_URL")

        self.APP_BASE_URL = self._required(
            "APP_BASE_URL"
        ).rstrip("/")

        self.OPENAI_API_KEY = os.getenv(
            "OPENAI_API_KEY"
        )

        cors_raw = os.getenv(
            "CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000"
        )

        self.CORS_ORIGINS = [
            origin.strip()
            for origin in cors_raw.split(",")
            if origin.strip()
        ]

        self.FORCE_EMAIL_FAILURE = (
            os.getenv(
                "FORCE_EMAIL_FAILURE",
                "false"
            ).strip().lower() == "true"
        )

    @staticmethod
    def _required(name: str) -> str:
        value = os.getenv(name)

        if value is None or not value.strip():
            raise RuntimeError(
                f"{name} is not configured"
            )

        return value.strip()


settings = Settings()