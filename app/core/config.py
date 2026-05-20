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
    alembic_ini_path: Path = Path("alembic.ini")


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
        alembic_ini_path=Path(os.getenv("AI_BLUEPRINT_ALEMBIC_INI", "alembic.ini")),
    )
