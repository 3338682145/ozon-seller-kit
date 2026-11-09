"""worker leases have explicit expiry to permit safe crash recovery.

Revision ID: 72d0e451ab02
Revises: 5f4922bf2679
"""
from alembic import op
import sqlalchemy as sa
revision = '72d0e451ab02'
down_revision = '5f4922bf2679'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('collection_jobs', sa.Column('lease_expires_at', sa.DateTime(timezone=True)))

def downgrade():
    op.drop_column('collection_jobs', 'lease_expires_at')
