"""shared category links

Revision ID: c7d9d692529a
Revises: b27eace77f79
Create Date: 2026-10-19 13:18:59.931723

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d9d692529a'
down_revision: Union[str, None] = 'b27eace77f79'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('shared_category_links',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('shared_budget_id', sa.Integer(), nullable=False),
    sa.Column('shared_category_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('shared_budget_id', 'category_id', name='uq_shared_link_category')
    )


def downgrade() -> None:
    op.drop_table('shared_category_links')
