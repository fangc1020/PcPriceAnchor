import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from price_monitor.models import Platform, Product, RamSpec

logger = logging.getLogger(__name__)


class ProductRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def upsert_product(self, clean_product) -> int:
        """幂等 upsert 商品主表 + 规格表，返回 product.id。

        Args:
            clean_product: CleanProduct schema instance.
        """
        # 1. 确定 platform_id (lookup or create)
        platform_id = await self._get_or_create_platform(
            clean_product.platform_code
        )

        # 2. Upsert product row
        product = await self._upsert_product_row(platform_id, clean_product)

        # 3. Upsert ram_spec if spec exists
        if clean_product.spec:
            await self._upsert_ram_spec(product.id, clean_product)

        await self._session.commit()
        return product.id

    async def _get_or_create_platform(self, code: str) -> int:
        result = await self._session.execute(
            select(Platform.id).where(Platform.code == code)
        )
        pid = result.scalar_one_or_none()
        if pid is not None:
            return pid

        platform = Platform(
            code=code,
            name=code,
            base_url=f"https://www.{code}.com",
        )
        self._session.add(platform)
        await self._session.flush()
        return platform.id

    async def _upsert_product_row(self, platform_id: int, clean_product) -> Product:
        result = await self._session.execute(
            select(Product).where(
                Product.platform_id == platform_id,
                Product.platform_sku_id == clean_product.platform_sku_id,
            )
        )
        product = result.scalar_one_or_none()

        if product is None:
            product = Product(
                platform_id=platform_id,
                platform_sku_id=clean_product.platform_sku_id,
                category=clean_product.category,
                brand=clean_product.brand,
                model=clean_product.model,
                title=clean_product.title,
                canonical_url=clean_product.canonical_url,
            )
            self._session.add(product)
            await self._session.flush()
        else:
            product.category = clean_product.category
            product.brand = clean_product.brand
            product.model = clean_product.model
            product.title = clean_product.title
            product.canonical_url = clean_product.canonical_url
            product.updated_at = datetime.now(timezone.utc)

        return product

    async def _upsert_ram_spec(self, product_id: int, clean_product) -> None:
        spec = clean_product.spec
        result = await self._session.execute(
            select(RamSpec).where(RamSpec.product_id == product_id)
        )
        existing = result.scalar_one_or_none()

        if existing is None:
            ram_spec = RamSpec(
                product_id=product_id,
                capacity_gb=spec.capacity_gb,
                kit_count=spec.kit_count,
                speed_mhz=spec.speed_mhz,
                cl_latency=spec.cl_latency,
                timing_string=spec.timing_string,
                die_type=spec.die_type,
                memory_type=spec.memory_type,
                form_factor=spec.form_factor,
                has_rgb=spec.has_rgb,
                xmp_version=spec.xmp_version,
                expo_supported=spec.expo_supported,
                parse_confidence=spec.parse_confidence,
            )
            self._session.add(ram_spec)
        else:
            existing.capacity_gb = spec.capacity_gb
            existing.kit_count = spec.kit_count
            existing.speed_mhz = spec.speed_mhz
            existing.cl_latency = spec.cl_latency
            existing.timing_string = spec.timing_string
            existing.die_type = spec.die_type
            existing.memory_type = spec.memory_type
            existing.form_factor = spec.form_factor
            existing.has_rgb = spec.has_rgb
            existing.xmp_version = spec.xmp_version
            existing.expo_supported = spec.expo_supported
            existing.parse_confidence = spec.parse_confidence

    async def get_by_platform_sku(
        self, platform_code: str, platform_sku_id: str
    ) -> dict | None:
        result = await self._session.execute(
            select(Product, Platform, RamSpec)
            .join(Platform, Product.platform_id == Platform.id)
            .outerjoin(RamSpec, Product.id == RamSpec.product_id)
            .where(
                Platform.code == platform_code,
                Product.platform_sku_id == platform_sku_id,
            )
        )
        row = result.one_or_none()
        if row is None:
            return None
        product, platform, ram_spec = row
        return {
            "id": product.id,
            "platform_code": platform.code,
            "platform_sku_id": product.platform_sku_id,
            "category": product.category,
            "brand": product.brand,
            "model": product.model,
            "title": product.title,
            "spec": {
                "capacity_gb": ram_spec.capacity_gb,
                "kit_count": ram_spec.kit_count,
                "total_gb": ram_spec.capacity_gb * ram_spec.kit_count,
                "speed_mhz": ram_spec.speed_mhz,
                "memory_type": ram_spec.memory_type,
                "die_type": ram_spec.die_type,
            } if ram_spec else None,
        }
