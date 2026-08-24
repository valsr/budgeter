"""budget lines can name an account

Revision ID: 1ed80c4a4e60
Revises: ca1a41854d07
Create Date: 2026-08-24 15:23:13.723834

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1ed80c4a4e60'
down_revision: Union[str, None] = 'ca1a41854d07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """A budget line can now name an account, so a category can be planned per
    source. Existing lines get NULL, which means "the whole category" -- the
    behaviour they already had.

    Batch mode: SQLite can't ALTER a table to add a foreign key or to swap a
    unique constraint, so Alembic rebuilds the table. The old
    uq_budget_category was (budget_id, category_id); it has to widen to
    include account_id or a category could hold only one line.
    """
    with op.batch_alter_table("budget_categories") as batch:
        batch.add_column(sa.Column("account_id", sa.Integer(), nullable=True))
        batch.drop_constraint("uq_budget_category", type_="unique")
        batch.create_unique_constraint(
            "uq_budget_category", ["budget_id", "category_id", "account_id"]
        )
        batch.create_foreign_key(
            "fk_budget_categories_account_id", "accounts", ["account_id"], ["id"]
        )


def downgrade() -> None:
    # Per-account lines have no category-level equivalent, so collapsing them
    # would silently merge or drop budgeted amounts. Drop the column only when
    # nothing uses it; otherwise refuse rather than corrupt the budget.
    conn = op.get_bind()
    per_account = conn.execute(
        sa.text("SELECT COUNT(*) FROM budget_categories WHERE account_id IS NOT NULL")
    ).scalar_one()
    if per_account:
        raise RuntimeError(
            f"{per_account} budget line(s) name an account; delete or convert them "
            "to category-level lines before downgrading"
        )
    with op.batch_alter_table("budget_categories") as batch:
        batch.drop_constraint("fk_budget_categories_account_id", type_="foreignkey")
        batch.drop_constraint("uq_budget_category", type_="unique")
        batch.create_unique_constraint("uq_budget_category", ["budget_id", "category_id"])
        batch.drop_column("account_id")
