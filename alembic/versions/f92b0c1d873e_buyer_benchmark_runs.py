"""buyer benchmark runs, intervals and samples.

Revision ID: f92b0c1d873e
Revises: 78a91cdf1b16

Creates the three independent audit tables for the V2 buyer 12-hour benchmark.
These are NOT product/keyword master tables; they only persist run metadata,
15-minute aggregated windows and a strictly-quota'd set of de-identified
observations. Review body / author / cookie bytes are never columns here.
"""
from alembic import op
import sqlalchemy as sa

revision = 'f92b0c1d873e'
down_revision = '78a91cdf1b16'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'benchmark_runs',
        sa.Column('run_id', sa.String(length=64), nullable=False),
        sa.Column('kind', sa.String(length=24), nullable=False),
        sa.Column('source_id', sa.String(length=64), nullable=False),
        sa.Column('mode', sa.String(length=16), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('stopped_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=24), nullable=False, server_default='running'),
        sa.Column('stop_reason', sa.String(length=256), nullable=True),
        sa.Column('policy_hash', sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint('run_id'),
    )
    op.create_table(
        'benchmark_intervals',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('run_id', sa.String(length=64), nullable=False),
        sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('requests', sa.Integer, nullable=False, server_default='0'),
        sa.Column('records', sa.Integer, nullable=False, server_default='0'),
        sa.Column('ok', sa.Integer, nullable=False, server_default='0'),
        sa.Column('empty_valid', sa.Integer, nullable=False, server_default='0'),
        sa.Column('empty_suspect', sa.Integer, nullable=False, server_default='0'),
        sa.Column('blocked', sa.Integer, nullable=False, server_default='0'),
        sa.Column('error', sa.Integer, nullable=False, server_default='0'),
        sa.Column('latency_p50_ms', sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column('latency_p95_ms', sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column('latency_p99_ms', sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column('bytes_received', sa.Integer, nullable=False, server_default='0'),
        sa.Column('valid_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('invalid_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('unknown_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('missing_field_rates', sa.JSON, nullable=True),
        sa.Column('schema_version', sa.String(length=32), nullable=True),
        sa.Column('policy_version', sa.String(length=32), nullable=True),
        sa.Column('audit_event_count', sa.Integer, nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['run_id'], ['benchmark_runs.run_id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id', 'window_start', name='uq_benchmark_interval_window'),
    )
    op.create_table(
        'benchmark_samples',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('run_id', sa.String(length=64), nullable=False),
        sa.Column('kind', sa.String(length=24), nullable=False),
        sa.Column('source_id', sa.String(length=64), nullable=False),
        sa.Column('sku', sa.String(length=64), nullable=False),
        sa.Column('page_path', sa.String(length=512), nullable=False),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('value', sa.JSON, nullable=False),
        sa.Column('raw_sha256', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['benchmark_runs.run_id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('benchmark_samples')
    op.drop_table('benchmark_intervals')
    op.drop_table('benchmark_runs')
