from typing import Any, List

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "Tax-Agent API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "tax_agent"

    FIREBASE_CREDENTIALS_PATH: str = "./firebase-admin-key.json"
    FIREBASE_STORAGE_BUCKET: str = ""
    FIREBASE_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    DEFAULT_AI_MODEL: str = "claude-sonnet-4-6"

    LAW_AGENT_URL: str = "http://localhost:8001"

    # SendGrid
    SENDGRID_API_KEY: str = ""
    SENDGRID_FROM_EMAIL: str = "noreply@tax-agent.app"
    APP_BASE_URL: str = "http://localhost:5173"

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    ENVIRONMENT: str = "development"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # Admin UID list (comma-separated in env: ADMIN_UIDS=uid1,uid2)
    ADMIN_UIDS: List[str] = []

    @field_validator("ADMIN_UIDS", mode="before")
    @classmethod
    def parse_admin_uids(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            return [uid.strip() for uid in v.split(",") if uid.strip()]
        return v or []

    class Config:
        env_file = ".env"


settings = Settings()

DEFAULT_TAX_RATE: int = 10  # デフォルト消費税率（%）
