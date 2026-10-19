"""widen rule_conditions.operator to fit every operator

Revision ID: e4a1f0c2b7d9
Revises: c7d9d692529a
Create Date: 2026-10-19 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4a1f0c2b7d9'
down_revision: Union[str, None] = 'c7d9d692529a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 8ae88b559671 skipped widening this column to VARCHAR(13) for IS_WITHDRAWAL, since SQLite
    # ignores declared lengths. Harmless at runtime, but autogenerate then re-proposed the change
    # on every revision. Rebuilding this one small table in batch mode settles it.
    with op.batch_alter_table("rule_conditions") as batch_op:
        batch_op.alter_column(
            "operator",
            existing_type=sa.VARCHAR(length=12),
            type_=sa.Enum(
                "CONTAINS",
                "NOT_CONTAINS",
                "EQUALS",
                "LESS_THAN",
                "GREATER_THAN",
                "IS_DEPOSIT",
                "IS_WITHDRAWAL",
                "IN",
                "NOT_IN",
                name="conditionoperator",
                native_enum=False,
                create_constraint=False,
            ),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("rule_conditions") as batch_op:
        batch_op.alter_column(
            "operator",
            existing_type=sa.VARCHAR(length=13),
            type_=sa.VARCHAR(length=12),
            existing_nullable=False,
        )
