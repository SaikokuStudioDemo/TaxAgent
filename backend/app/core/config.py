from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Tax-Agent API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "tax_agent"

    FIREBASE_CREDENTIALS_PATH: str = "./firebase-admin-key.json"
    FIREBASE_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    DEFAULT_AI_MODEL: str = "claude-sonnet-4-6"

    LAW_AGENT_URL: str = "http://localhost:8001"

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    ENVIRONMENT: str = "development"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    class Config:
        env_file = ".env"

settings = Settings()
