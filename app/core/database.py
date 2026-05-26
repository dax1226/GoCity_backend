from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

# Defaults to local PostgreSQL. Override via DATABASE_URL in .env.
#   Postgres:  postgresql://postgres:password@localhost:5432/gocity
#   SQLite (dev only):  sqlite:///./gocity.db
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/gocity",
)

# SQLite needs check_same_thread=False; Postgres does not.
connect_args = (
    {"check_same_thread": False}
    if SQLALCHEMY_DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,  # auto-reconnect dropped Postgres connections
)


# Auto-enable PostGIS on Postgres connections (no-op for SQLite).
if SQLALCHEMY_DATABASE_URL.startswith("postgres"):
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
