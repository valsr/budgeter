"""never reuse user ids

Revision ID: 7c1d9a4e2b10
Revises: 3b3546522964
Create Date: 2026-10-07 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '7c1d9a4e2b10'
down_revision: Union[str, None] = '3b3546522964'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rebuild `users` with AUTOINCREMENT so a deleted user's id is never
    # given to a later account (plain INTEGER PRIMARY KEY reuses the highest
    # id). SQLite can't add this in place; batch mode copies the table.
    with op.batch_alter_table('users', recreate='always', table_kwargs={'sqlite_autoincrement': True}):
        pass


def downgrade() -> None:
    with op.batch_alter_table('users', recreate='always', table_kwargs={'sqlite_autoincrement': False}):
        pass
