from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/plfantasy"
    )
    cors_origins: str = "http://localhost:3006"
    # Regex alternative to the origin list, for Vercel preview deployments whose
    # URLs are generated per-commit (e.g. ^https://myapp-.*\.vercel\.app$).
    cors_origin_regex: str = ""
    fpl_api_base: str = "https://fantasy.premierleague.com/api"

    # Supabase auth. supabase_url is the project API URL and doubles as the JWT
    # issuer and JWKS host. supabase_jwt_secret is only needed by older projects
    # that still sign tokens with a shared HS256 secret.
    supabase_url: str = ""
    supabase_jwt_secret: str = ""

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
