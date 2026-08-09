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
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)

if settings.database_url.startswith("sqlite"):
    # SQLite ignores ForeignKey() constraints unless this pragma is set
    # per-connection. Without it, dev/test runs can silently insert rows
    # that reference a nonexistent fighter/fight/etc — a bug that would
    # only surface later, in production, on Postgres (which always
    # enforces FKs). Turning this on keeps SQLite's behavior honest.
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
