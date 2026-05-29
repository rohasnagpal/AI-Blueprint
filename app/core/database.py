from collections.abc import Generator

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

_engine: Engine | None = None
_engine_url: str | None = None
_SessionFactory: sessionmaker[Session] | None = None


class Base(DeclarativeBase):
    pass


def _build_engine() -> Engine:
    settings = get_settings()
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    engine = create_engine(settings.database_url, connect_args=connect_args, future=True)

    if settings.database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def get_engine() -> Engine:
    global _engine, _engine_url, _SessionFactory
    settings = get_settings()
    if _engine is None or _engine_url != settings.database_url:
        if _engine is not None:
            _engine.dispose()
        _engine = _build_engine()
        _engine_url = settings.database_url
        _SessionFactory = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


class _SessionLocalProxy:
    def __call__(self) -> Session:
        global _SessionFactory
        get_engine()
        assert _SessionFactory is not None
        return _SessionFactory()


SessionLocal = _SessionLocalProxy()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def run_migrations() -> None:
    settings = get_settings()
    cfg = Config(str(settings.alembic_ini_path))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(cfg, "head")
