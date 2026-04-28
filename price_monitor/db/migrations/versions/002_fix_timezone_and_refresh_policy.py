"""Fix continuous aggregate: timezone-aware bucketing + auto-refresh policy

Revision ID: 002
Revises: 001
Create Date: 2026-04-29
"""
from typing import Sequence, Union
from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop old aggregate (source data in price_ticks is safe)
    op.execute("DROP MATERIALIZED VIEW IF EXISTS price_hourly CASCADE")

    # Recreate with Asia/Shanghai timezone bucketing
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS price_hourly
        WITH (timescaledb.continuous) AS
        SELECT
            product_id,
            time_bucket('1 hour', recorded_at, 'Asia/Shanghai') AS bucket,
            MIN(price_fen - coupon_fen) AS min_final_fen,
            MAX(price_fen - coupon_fen) AS max_final_fen,
            AVG(price_fen - coupon_fen) AS avg_final_fen,
            COUNT(*) AS tick_count
        FROM price_ticks
        GROUP BY product_id, bucket
        WITH NO DATA
    """)

    # Add auto-refresh policy: refresh every 30 min, covering last 4 hours
    op.execute("""
        SELECT add_continuous_aggregate_policy('price_hourly',
            start_offset    => INTERVAL '4 hours',
            end_offset      => INTERVAL '1 hour',
            schedule_interval => INTERVAL '30 minutes',
            if_not_exists   => TRUE
        )
    """)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS price_hourly CASCADE")
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS price_hourly
        WITH (timescaledb.continuous) AS
        SELECT
            product_id,
            time_bucket('1 hour', recorded_at) AS bucket,
            MIN(price_fen - coupon_fen) AS min_final_fen,
            MAX(price_fen - coupon_fen) AS max_final_fen,
            AVG(price_fen - coupon_fen) AS avg_final_fen,
            COUNT(*) AS tick_count
        FROM price_ticks
        GROUP BY product_id, bucket
        WITH NO DATA
    """)
