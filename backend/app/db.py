from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def upgrade_to_head() -> None:
    """Bring the database schema up to the latest Alembic revision.

    Called on app startup (see main.py's lifespan) so a stale or missing
    schema — a fresh checkout, or a migration added since the DB file was
    last touched — self-heals instead of failing with "no such table" the
    first time a new column/table is queried. The bare in-memory sqlite URL
    is the test suite's sentinel (see tests/conftest.py); it skips this and
    creates tables directly via Base.metadata.create_all instead, since a
    fresh in-memory DB is created per test run anyway.
    """
    if settings.database_url == "sqlite://":
        return
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config(str(_ALEMBIC_INI)), "head")
