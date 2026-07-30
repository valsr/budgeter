"""add amount direction condition operators

Revision ID: 8ae88b559671
Revises: 2505b64e181c
Create Date: 2026-07-29 22:34:06.213710

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8ae88b559671'
down_revision: Union[str, None] = '2505b64e181c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Autogenerate wanted to widen rule_conditions.operator from VARCHAR(12)
    # to VARCHAR(13) (SQLAlchemy sizes the column to the longest enum value,
    # and "is_withdrawal" is longer than the previous longest, "not_contains").
    # This is a no-op on SQLite: there's no native ENUM type and no CHECK
    # constraint on this column (see cecb48c9cea2's migration -- it created
    # the column as a bare VARCHAR), and SQLite's dynamic typing ignores
    # declared column length entirely, so existing/new values both fit
    # regardless. The plain (non-batch) ALTER COLUMN TYPE Alembic generated
    # for this also isn't valid SQL on SQLite, which doesn't support it
    # outside of batch mode -- and batch mode would mean rebuilding the
    # whole table for a change that has no runtime effect. Skipping it.
    pass


def downgrade() -> None:
    pass
