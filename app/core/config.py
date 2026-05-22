from functools import lru_cache
import os
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    database_url: str = "sqlite:///./ai_blueprint_v2.db"
    uploads_dir: Path = Path("uploads_v2")
    secret_key_file: Path = Path(".secret_key_v2")
    session_cookie_name: str = "ai_blueprint_session"
    session_days: int = 14
    secure_cookies: bool = False
    bootstrap_default_admin: bool = False
    cors_origins: list[str] = ["http://localhost:8000", "http://127.0.0.1:8000"]
    max_upload_bytes: int = 25 * 1024 * 1024
    auth_rate_limit_attempts: int = 10
    auth_rate_limit_window_seconds: int = 60
    alembic_ini_path: Path = Path("alembic.ini")


def _csv_env(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("AI_BLUEPRINT_DATABASE_URL", "sqlite:///./ai_blueprint_v2.db"),
        uploads_dir=Path(os.getenv("AI_BLUEPRINT_UPLOADS_DIR", "uploads_v2")),
        secret_key_file=Path(os.getenv("AI_BLUEPRINT_SECRET_KEY_FILE", ".secret_key_v2")),
        session_cookie_name=os.getenv("AI_BLUEPRINT_SESSION_COOKIE", "ai_blueprint_session"),
        session_days=int(os.getenv("AI_BLUEPRINT_SESSION_DAYS", "14")),
        secure_cookies=os.getenv("AI_BLUEPRINT_SECURE_COOKIES", "false").lower() == "true",
        bootstrap_default_admin=os.getenv("AI_BLUEPRINT_BOOTSTRAP_DEFAULT_ADMIN", "false").lower() == "true",
        cors_origins=_csv_env("AI_BLUEPRINT_CORS_ORIGINS", ["http://localhost:8000", "http://127.0.0.1:8000"]),
        max_upload_bytes=int(os.getenv("AI_BLUEPRINT_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024))),
        auth_rate_limit_attempts=int(os.getenv("AI_BLUEPRINT_AUTH_RATE_LIMIT_ATTEMPTS", "10")),
        auth_rate_limit_window_seconds=int(os.getenv("AI_BLUEPRINT_AUTH_RATE_LIMIT_WINDOW_SECONDS", "60")),
        alembic_ini_path=Path(os.getenv("AI_BLUEPRINT_ALEMBIC_INI", "alembic.ini")),
    )
