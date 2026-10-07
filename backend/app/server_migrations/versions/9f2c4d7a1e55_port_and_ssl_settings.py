"""port and ssl settings

Revision ID: 9f2c4d7a1e55
Revises: 7c1d9a4e2b10
Create Date: 2026-10-08 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f2c4d7a1e55'
down_revision: Union[str, None] = '7c1d9a4e2b10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('server_settings', sa.Column('port', sa.Integer(), server_default='8000', nullable=False))
    op.add_column('server_settings', sa.Column('ssl_enabled', sa.Boolean(), server_default='0', nullable=False))
    op.add_column('server_settings', sa.Column('ssl_certfile', sa.String(length=1000), nullable=True))
    op.add_column('server_settings', sa.Column('ssl_keyfile', sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column('server_settings', 'ssl_keyfile')
    op.drop_column('server_settings', 'ssl_certfile')
    op.drop_column('server_settings', 'ssl_enabled')
    op.drop_column('server_settings', 'port')
