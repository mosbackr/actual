from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://acutal:acutal@localhost:5432/acutal"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001", "http://98.89.232.52:3000", "http://98.89.232.52:3001", "https://deepthesis.org", "https://admin.deepthesis.org", "https://www.deepthesis.org"]
    admin_setup_key: str = "acutal-setup-2024"
    logo_dev_token: str = ""
    perplexity_api_key: str = ""
    anthropic_api_key: str = ""
    database_readonly_url: str = ""
    edgar_user_agent: str = "Acutal admin@deepthesis.org"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    s3_bucket_name: str = "deepthesis-pitch-documents"

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_starter: str = ""
    stripe_price_professional: str = ""
    stripe_price_unlimited: str = ""
    frontend_url: str = "https://deepthesis.org"
    promo_code_unlimited: str = "DEEPTHESIS2026"

    # Email (Resend)
    resend_api_key: str = ""
    email_from: str = "gaius@deepthesis.org"

    model_config = {"env_prefix": "ACUTAL_"}


settings = Settings()
