"""drop api key table

Revision ID: b27eace77f79
Revises: 1ed80c4a4e60
Create Date: 2026-10-07 10:56:18.160974

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b27eace77f79'
down_revision: Union[str, None] = '1ed80c4a4e60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # API keys are per user now, hashed, in the server database
    # (users.api_key_hash). books.claim_legacy_books reads the old shared
    # key out of a pre-accounts database before this runs on its copy.
    op.drop_table('api_key')


def downgrade() -> None:
    op.create_table('api_key',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('key', sa.VARCHAR(length=128), nullable=False),
    sa.Column('updated_at', sa.DATETIME(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
