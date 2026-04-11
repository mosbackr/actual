from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://acutal:acutal@localhost:5432/acutal"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001", "http://18.212.88.189:3000", "http://18.212.88.189:3001"]
    admin_setup_key: str = "acutal-setup-2024"
    logo_dev_token: str = ""
    perplexity_api_key: str = ""

    model_config = {"env_prefix": "ACUTAL_"}


settings = Settings()
