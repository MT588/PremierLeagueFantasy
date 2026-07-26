from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/plfantasy"
    cors_origins: str = "http://localhost:3000"
    fpl_api_base: str = "https://fantasy.premierleague.com/api"


settings = Settings()
