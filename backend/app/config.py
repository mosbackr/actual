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
    edgar_user_agent: str = "Acutal admin@deepthesis.org"

    model_config = {"env_prefix": "ACUTAL_"}


settings = Settings()
