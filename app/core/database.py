from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

DEFAULT_SQLITE_URL = "sqlite:///./gocity.db"

def _clean_url(value: str | None, fallback: str) -> str:
    if not value:
        return fallback
    stripped = value.strip()
    if (
        (stripped.startswith('"') and stripped.endswith('"'))
        or (stripped.startswith("'") and stripped.endswith("'"))
    ):
        stripped = stripped[1:-1].strip()
    return stripped or fallback


def _connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    if url.startswith("postgresql"):
        # Keep startup failures quick when remote DB is down/unreachable.
        return {"connect_timeout": 5}
    return {}


def _build_engine(url: str):
    return create_engine(
        url,
        connect_args=_connect_args(url),
        pool_pre_ping=True,  # auto-reconnect dropped DB connections
    )


def _can_connect(test_engine) -> bool:
    try:
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False


configured_database_url = _clean_url(os.getenv("DATABASE_URL"), DEFAULT_SQLITE_URL)
fallback_database_url = _clean_url(os.getenv("DATABASE_FALLBACK_URL"), DEFAULT_SQLITE_URL)

active_database_url = configured_database_url
engine = _build_engine(active_database_url)

if active_database_url.startswith("postgresql") and not _can_connect(engine):
    print(
        "[DB] Could not connect to configured Postgres DB. "
        f"Falling back to {fallback_database_url}."
    )
    active_database_url = fallback_database_url
    engine = _build_engine(active_database_url)

    if active_database_url.startswith("postgresql") and not _can_connect(engine):
        print(
            "[DB] Fallback Postgres is also unreachable. "
            f"Using local SQLite at {DEFAULT_SQLITE_URL}."
        )
        active_database_url = DEFAULT_SQLITE_URL
        engine = _build_engine(active_database_url)

# Auto-enable PostGIS on Postgres connections (no-op for SQLite).
if active_database_url.startswith("postgres"):
    @event.listens_for(engine, "connect")
    def _ensure_postgis(dbapi_connection, _connection_record):
        try:
            cur = dbapi_connection.cursor()
            cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
            dbapi_connection.commit()
            cur.close()
        except Exception:
            # User may lack superuser rights — they can run it manually.
            dbapi_connection.rollback()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
