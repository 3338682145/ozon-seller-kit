"""record incident last occurrence for dedup and re-escalation.

Revision ID: 78a91cdf1b16
Revises: 72d0e451ab02
"""
from alembic import op
import sqlalchemy as sa

revision = '78a91cdf1b16'
down_revision = '72d0e451ab02'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('incidents', sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    if op.get_bind().dialect.name != 'sqlite':
        op.alter_column('incidents', 'last_seen_at', server_default=None)


def downgrade():
    op.drop_column('incidents', 'last_seen_at')
