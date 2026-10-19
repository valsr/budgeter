"""The shared budget files: one SQLite file per shared budget, all with the same schema."""

from sqlalchemy.orm import DeclarativeBase


class SharedBase(DeclarativeBase):
    pass
