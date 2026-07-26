from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/plfantasy"
    )
    cors_origins: str = "http://localhost:3000"
    fpl_api_base: str = "https://fantasy.premierleague.com/api"

    @field_validator("database_url")
    @classmethod
    def coerce_psycopg_driver(cls, v: str) -> str:
        # Accept connection strings pasted straight from the Supabase dashboard
        # (postgres:// or postgresql://) by pinning the psycopg3 driver.
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+psycopg://", 1)
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+psycopg://", 1)
        return v


settings = Settings()
