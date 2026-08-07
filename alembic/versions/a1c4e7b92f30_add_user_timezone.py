"""add users.timezone

Stores the IANA timezone name read from the user's primary Google Calendar at
login. Nullable because the lookup can fail and must not block sign-in; callers
fall back to config.TIMEZONE.

Revision ID: a1c4e7b92f30
Revises: 36522ddf1911
Create Date: 2026-08-06 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1c4e7b92f30'
down_revision: Union[str, Sequence[str], None] = '36522ddf1911'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("timezone", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "timezone")
