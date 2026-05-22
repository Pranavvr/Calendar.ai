"""initial users and google_credentials tables

Revision ID: 36522ddf1911
Revises: 
Create Date: 2026-05-18 18:08:11.166804

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '36522ddf1911'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id",          sa.Uuid(),                       primary_key=True),
        sa.Column("google_sub",  sa.Text(),                       nullable=False, unique=True),
        sa.Column("email",       sa.Text(),                       nullable=False, unique=True),
        sa.Column("name",        sa.Text(),                       nullable=True),
        sa.Column("picture_url", sa.Text(),                       nullable=True),
        sa.Column("created_at",  sa.TIMESTAMP(timezone=True),     nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at",  sa.TIMESTAMP(timezone=True),     nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "google_credentials",
        sa.Column("user_id",       sa.Uuid(),                     sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("refresh_token", sa.Text(),                     nullable=False),
        sa.Column("scope",         sa.Text(),                     nullable=False),
        sa.Column("updated_at",    sa.TIMESTAMP(timezone=True),   nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("google_credentials")
    op.drop_table("users")
