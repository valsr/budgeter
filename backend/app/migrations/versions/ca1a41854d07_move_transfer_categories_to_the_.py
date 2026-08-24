"""move transfer categories to the withdrawal leg

Revision ID: ca1a41854d07
Revises: 4f99a86db343
Create Date: 2026-08-24 14:52:22.768621

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ca1a41854d07'
down_revision: Union[str, None] = '4f99a86db343'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """A linked transfer's category now always lives on its withdrawal leg,
    so the same movement reads the same way however it was linked (see
    transactions._category_leg). Pairs categorized before that rule was fixed
    may hold it on the deposit leg, where it reports with the opposite sign --
    a contribution showing as a credit rather than a charge. Move them.

    Only the sign convention changes; no category is added or removed, and a
    pair whose category is already on the withdrawal leg is untouched.
    SQLAlchemy's Enum stores the member name, hence 'TRANSFER'."""
    conn = op.get_bind()
    misplaced = conn.execute(
        sa.text(
            """
            SELECT t.id AS leg_id,
                   t.transfer_pair_id AS pair_id,
                   MAX(s.category_id) AS category_id
            FROM transactions t
            JOIN splits s ON s.transaction_id = t.id
            WHERE t.type = 'TRANSFER'
              AND t.transfer_pair_id IS NOT NULL
              AND s.category_id IS NOT NULL
            GROUP BY t.id, t.transfer_pair_id
            HAVING SUM(s.amount) > 0
            """
        )
    ).fetchall()

    for leg_id, pair_id, category_id in misplaced:
        conn.execute(
            sa.text(
                "UPDATE splits SET category_id = NULL, suggested_category_id = NULL, "
                "suggestion_source = NULL WHERE transaction_id = :leg_id"
            ),
            {"leg_id": leg_id},
        )
        conn.execute(
            sa.text("UPDATE splits SET category_id = :category_id WHERE transaction_id = :pair_id"),
            {"category_id": category_id, "pair_id": pair_id},
        )


def downgrade() -> None:
    # Which leg a category sat on before is not recorded anywhere, so there is
    # nothing to put back. Leaving the categories where they are keeps the
    # data valid under the old rule too -- it just reports the newer sign.
    pass
