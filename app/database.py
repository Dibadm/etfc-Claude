"""
Database engine and session management.

Dev/test default is SQLite (zero setup). For production, set
ETFC_DATABASE_URL to a Postgres connection string.

IMPORTANT — SQLite vs Postgres for money handling:
Bet placement and settlement both rely on row-level locking
(SELECT ... FOR UPDATE) to make "check balance, then debit" and
"settle every bet on a market" atomic under concurrent load. SQLite
does not support real row-level locking — it serializes at the
database-file level instead. That's fine for local development and
the tests in this repo, but production MUST run on Postgres before
real money is involved, or two simultaneous bets/settlements can race.
The `with_for_update()` calls in the services below are silently
no-ops on SQLite and fully enforced on Postgres.
"""
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_pre_ping=True,
)

if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    if settings.database_url.startswith("sqlite"):
        result = conn.execute(text(f"PRAGMA table_info({table_name})"))
        return any(row[1] == column_name for row in result)
    result = conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :column"
        ),
        {"table": table_name, "column": column_name},
    )
    return result.fetchone() is not None


def _ensure_columns():
    with engine.begin() as conn:
        if not _column_exists(conn, "users", "phone"):
            conn.execute(text("ALTER TABLE users ADD COLUMN phone VARCHAR(255)"))
        if not _column_exists(conn, "wallet_transactions", "idempotency_key"):
            conn.execute(text("ALTER TABLE wallet_transactions ADD COLUMN idempotency_key VARCHAR(255)"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_wallet_transactions_idempotency_key ON wallet_transactions (idempotency_key)"))


_ensure_columns()
