"""Initial schema: platforms, products, ram_specs, price_ticks hypertable

Revision ID: 001
Revises:
Create Date: 2026-04-27
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platforms",
        sa.Column("id", sa.SmallInteger, primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(20), unique=True, nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("base_url", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("platform_id", sa.SmallInteger, sa.ForeignKey("platforms.id"), nullable=False),
        sa.Column("platform_sku_id", sa.String(64), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("brand", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("canonical_url", sa.String(500)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("TRUE")),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("platform_id", "platform_sku_id", name="uq_platform_sku"),
        sa.Index("idx_products_category_brand", "category", "brand"),
    )

    op.create_table(
        "ram_specs",
        sa.Column("product_id", sa.BigInteger, sa.ForeignKey("products.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("capacity_gb", sa.SmallInteger, nullable=False),
        sa.Column("kit_count", sa.SmallInteger, nullable=False, server_default=sa.text("1")),
        sa.Column("speed_mhz", sa.Integer, nullable=False),
        sa.Column("cl_latency", sa.SmallInteger),
        sa.Column("timing_string", sa.String(30)),
        sa.Column("die_type", sa.String(20)),
        sa.Column("memory_type", sa.String(10), nullable=False),
        sa.Column("form_factor", sa.String(10), nullable=False, server_default=sa.text("'DIMM'")),
        sa.Column("has_rgb", sa.Boolean, nullable=False, server_default=sa.text("FALSE")),
        sa.Column("heatspreader", sa.Boolean, nullable=False, server_default=sa.text("TRUE")),
        sa.Column("color", sa.String(30)),
        sa.Column("xmp_version", sa.String(10)),
        sa.Column("expo_supported", sa.Boolean, nullable=False, server_default=sa.text("FALSE")),
        sa.Column("parsed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("parse_confidence", sa.Numeric(3, 2), nullable=False, server_default=sa.text("1.00")),
        sa.Index("idx_ram_specs_type_speed", "memory_type", "speed_mhz"),
        sa.Index("idx_ram_specs_capacity", "capacity_gb"),
    )

    op.create_table(
        "price_ticks",
        sa.Column("id", sa.BigInteger, autoincrement=True),
        sa.Column("product_id", sa.BigInteger, sa.ForeignKey("products.id"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("price_fen", sa.Integer, nullable=False),
        sa.Column("original_fen", sa.Integer),
        sa.Column("coupon_fen", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("in_stock", sa.Boolean, nullable=False, server_default=sa.text("TRUE")),
        sa.Column("promotion_tag", sa.String(100)),
        sa.Column("crawler_version", sa.String(20), nullable=False),
        sa.Column("raw_hash", sa.String(64)),
        sa.PrimaryKeyConstraint("id", "recorded_at"),
        sa.Index("idx_price_ticks_product", "product_id", "recorded_at"),
    )

    # TimescaleDB hypertable conversion (requires TimescaleDB extension)
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    op.execute(
        "SELECT create_hypertable('price_ticks', 'recorded_at', "
        "chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE)"
    )

    # Continuous aggregate: hourly price summary
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


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS price_hourly CASCADE")
    op.drop_table("price_ticks")
    op.drop_table("ram_specs")
    op.drop_table("products")
    op.drop_table("platforms")
