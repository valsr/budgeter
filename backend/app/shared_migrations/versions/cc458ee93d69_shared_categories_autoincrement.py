"""shared categories autoincrement

Members' links to shared categories live in their own books, out of reach of this file's
cascades, so a deleted shared category's id must never be handed out again. SQLite only
guarantees that with AUTOINCREMENT, which can only be added by recreating the table.
Autogenerate doesn't see the difference, so this one is handwritten.

Revision ID: cc458ee93d69
Revises: dbf1bbe8aec4
Create Date: 2026-10-19 14:24:00.049269

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cc458ee93d69'
down_revision: Union[str, None] = 'dbf1bbe8aec4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _foreign_keys_off() -> None:
    """The recreate drops the old table, and with foreign keys on that drop would cascade-delete
    every amount and tally. The migration connection doesn't turn them on, but make sure."""
    bind = op.get_bind()
    if bind.exec_driver_sql("PRAGMA foreign_keys").scalar():
        bind.exec_driver_sql("PRAGMA foreign_keys=OFF")  # a no-op inside a transaction, hence the check
        if bind.exec_driver_sql("PRAGMA foreign_keys").scalar():
            raise RuntimeError("Foreign keys must be off to recreate shared_categories")


def _recreate(autoincrement: bool) -> None:
    _foreign_keys_off()
    with op.batch_alter_table(
        'shared_categories', recreate='always', table_kwargs={'sqlite_autoincrement': autoincrement}
    ):
        pass


def upgrade() -> None:
    _recreate(True)


def downgrade() -> None:
    _recreate(False)
