"""account conditions use in/not_in

Revision ID: 4f99a86db343
Revises: 8ae88b559671
Create Date: 2026-08-24 12:17:38.930604

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f99a86db343'
down_revision: Union[str, None] = '8ae88b559671'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The account field now matches by set membership over account ids
    # (ConditionOperator.IN / NOT_IN) instead of EQUALS -- see the comment on
    # rule_engine.MEMBERSHIP_OPERATORS. Repoint every existing account
    # condition at IN, whatever operator it carried: the pre-IN editor only
    # ever offered EQUALS, but conditions written before that restriction
    # landed may hold CONTAINS/LESS_THAN/GREATER_THAN, all of which were only
    # ever comparing bare ids by accident.
    #
    # Values need no rewriting -- IN's storage form is a comma-separated id
    # list, and a lone "3" is already a valid one-element list.
    #
    # SQLAlchemy's Enum stores the member *name*, so these are the uppercase
    # forms. No schema change: rule_conditions.operator is a bare VARCHAR with
    # no CHECK constraint (see cecb48c9cea2), and SQLite ignores the declared
    # length, so the new values fit as-is.
    op.execute("UPDATE rule_conditions SET operator = 'IN' WHERE field = 'ACCOUNT'")


def downgrade() -> None:
    # A multi-account condition has no EQUALS equivalent, so only the
    # single-id ones can go back; the rest would silently change meaning.
    op.execute(
        "UPDATE rule_conditions SET operator = 'EQUALS' "
        "WHERE field = 'ACCOUNT' AND operator = 'IN' AND value NOT LIKE '%,%'"
    )
