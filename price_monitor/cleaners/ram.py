"""内存条清洗器 — 解析标题中的频率、时序、容量、颗粒等规格。"""

import hashlib
import json
import logging
import re
from datetime import datetime

from price_monitor.crawlers.schemas import RawProduct
from price_monitor.cleaners.base import BaseCleaner
from price_monitor.cleaners.normalizer import brand_normalizer
from price_monitor.cleaners.schemas import CleanProduct, RamSpec

logger = logging.getLogger(__name__)

# --- DDR 类型检测 ---
DDR5_PATTERN = re.compile(r"(?i)\bddr5\b")
DDR4_PATTERN = re.compile(r"(?i)\bddr4\b")

# --- 容量解析 ---
# (pattern, per_stick_group_index, kit_count_group_index)
# 顺序重要：先匹配 per×count 格式（中文常见），再匹配 count×per 格式
CAPACITY_KIT_PATTERNS: list[tuple[re.Pattern, int, int]] = [
    # "16G×2" or "32GB×2" or "16×2" — per × count (most common in Chinese titles)
    (re.compile(r"(\d+)\s*(?:GB?)?\s*[×xX]\s*(\d+)\b"), 0, 1),
    # "2×32GB" — count × per (GB attached to second number)
    (re.compile(r"(\d+)\s*[×xX]\s*(\d+)\s*GB\b"), 1, 0),
    # "64GB(2×32GB)" → per_stick=group 2, count=group 1
    (re.compile(r"(\d+)\s*GB\s*\(\s*(\d+)\s*[×xX]\s*(\d+)\s*GB?\s*\)"), 2, 1),
]

# 简单容量：无套装信息
CAPACITY_SIMPLE = re.compile(r"(\d+)\s*GB?\b")

# --- 频率解析 ---
SPEED_PATTERN = re.compile(r"(\d{4,5})\s*(?:MHz|mhz|MT/s|MTS)?")

# --- 时序解析 ---
CL_PATTERN = re.compile(r"(?i)\bCL\s*(\d{1,3})\b")
TIMING_PATTERN = re.compile(r"(\d{1,3})\s*-\s*(\d{1,3})\s*-\s*(\d{1,3})\s*-\s*(\d{1,3})")

# --- 外形 ---
SODIMM_PATTERN = re.compile(r"(?i)\bso[-]?dimm\b")
DIMM_PATTERN = re.compile(r"(?i)\bdimm\b")

# --- RGB 检测（不用 \b，中文不认单词边界）---
RGB_PATTERN = re.compile(r"(?i)(rgb|argb|幻锋|幻光|灯条|灯)")

# --- XMP / EXPO ---
XMP_PATTERN = re.compile(r"(?i)\bXMP\s*(\d+\.?\d*)?\b")
EXPO_PATTERN = re.compile(r"(?i)\bEXPO\b")

# --- 颗粒型号关键词库 ---
DIE_KEYWORDS: dict[str, list[str]] = {
    "Samsung B-die": ["b-die", "b die", "bdie", "三星bdie", "三星b-die"],
    "Samsung": ["三星", "samsung"],
    "Hynix M-die": ["m-die", "m die", "mdie", "海力士mdie", "海力士m-die"],
    "Hynix A-die": ["a-die", "a die", "adie", "海力士adie", "海力士a-die"],
    "SK Hynix": ["海力士", "hynix", "sk hynix", "skhynix"],
    "Micron": ["镁光", "micron", "美光"],
    "Nanya": ["南亚", "nanya"],
}

SPEC_BRAND_KEYWORDS = [
    "金士顿", "kingston", "芝奇", "g.skill", "海盗船", "corsair",
    "威刚", "adata", "英睿达", "crucial", "十铨", "teamgroup",
    "光威", "gloway", "玖合", "juhor", "阿斯加特", "asgard",
    "雷克沙", "lexar", "科赋", "klevv", "三星", "samsung",
    "镁光", "micron", "xpg", "zadak", "博帝", "patriot",
]


class RamCleaner(BaseCleaner):
    category = "ram"

    def clean(self, raw: RawProduct) -> CleanProduct | None:
        title = raw.title

        ram_spec = self._parse_ram_spec(title)
        if ram_spec is None:
            logger.info("RamCleaner: failed to parse RAM spec from title: %s", title)
            return None

        brand = self._extract_brand(title)
        model = self._extract_model(title, brand)
        raw_hash = self._compute_hash(raw)

        return CleanProduct(
            platform_code=raw.platform_code,
            platform_sku_id=raw.platform_sku_id,
            category=self.category,
            brand=brand,
            model=model,
            title=title,
            canonical_url=raw.detail_url,
            price_fen=raw.price_fen,
            original_fen=raw.original_fen,
            coupon_fen=raw.coupon_fen,
            in_stock=raw.in_stock,
            promotion_tag=raw.promotion_tag,
            spec=ram_spec,
            raw_hash=raw_hash,
            crawled_at=raw.crawled_at.isoformat(),
            crawler_version=raw.crawler_version,
        )

    def validate(self, product: CleanProduct) -> bool:
        if product.spec is None:
            return False
        if product.spec.parse_confidence < 0.8:
            return False
        if product.spec.speed_mhz < 800 or product.spec.speed_mhz > 12800:
            return False
        if product.spec.capacity_gb <= 0:
            return False
        if product.spec.memory_type not in ("DDR4", "DDR5"):
            return False
        if not product.brand or not product.model:
            return False
        return True

    def _parse_ram_spec(self, title: str) -> RamSpec | None:
        """从标题解析内存规格，返回 RamSpec 或 None。"""
        confidence = 1.0
        fields_found = 0

        # 1. DDR 类型
        memory_type = ""
        if DDR5_PATTERN.search(title):
            memory_type = "DDR5"
            fields_found += 1
        elif DDR4_PATTERN.search(title):
            memory_type = "DDR4"
            fields_found += 1
        else:
            # 尝试通过频率推断
            speed_match = SPEED_PATTERN.search(title)
            if speed_match:
                speed = int(speed_match.group(1))
                if speed >= 4800:
                    memory_type = "DDR5"
                    fields_found += 1
                elif speed <= 3600:
                    memory_type = "DDR4"
                    fields_found += 1

        if not memory_type:
            return None

        # 2. 频率
        speed_match = SPEED_PATTERN.search(title)
        speed_mhz = 0
        if speed_match:
            speed_mhz = int(speed_match.group(1))
            fields_found += 1
        else:
            confidence -= 0.3

        # 3. 容量
        capacity_gb = 0
        kit_count = 1
        # Try kit patterns first (they give both per-stick capacity and count)
        for pattern, per_idx, count_idx in CAPACITY_KIT_PATTERNS:
            cap_match = pattern.search(title)
            if cap_match:
                groups = cap_match.groups()
                capacity_gb = int(groups[per_idx])
                kit_count = int(groups[count_idx])
                fields_found += 1
                break
        # Fall back to simple capacity
        if capacity_gb == 0:
            simple_match = CAPACITY_SIMPLE.search(title)
            if simple_match:
                capacity_gb = int(simple_match.group(1))
                fields_found += 1

        if capacity_gb == 0:
            confidence -= 0.3

        # 4. CL 时序
        cl_latency = None
        cl_match = CL_PATTERN.search(title)
        if cl_match:
            cl_latency = int(cl_match.group(1))
            fields_found += 1

        # 5. 完整时序串
        timing_string = None
        timing_match = TIMING_PATTERN.search(title)
        if timing_match:
            timing_string = timing_match.group(0)
            fields_found += 1

        # 6. 外形
        form_factor = "DIMM"
        if SODIMM_PATTERN.search(title):
            form_factor = "SO-DIMM"

        # 7. RGB
        has_rgb = bool(RGB_PATTERN.search(title))

        # 8. XMP / EXPO
        xmp_version = None
        xmp_match = XMP_PATTERN.search(title)
        if xmp_match:
            version = xmp_match.group(1) or ""
            xmp_version = f"XMP {version}" if version else "XMP"

        expo_supported = bool(EXPO_PATTERN.search(title))

        # 9. 颗粒型号
        die_type = self._extract_die_type(title)
        if die_type:
            fields_found += 1

        # 置信度调整
        if fields_found < 3:
            confidence -= 0.2
        confidence = max(0.0, min(1.0, confidence))

        return RamSpec(
            capacity_gb=capacity_gb,
            kit_count=kit_count,
            speed_mhz=speed_mhz or 0,
            cl_latency=cl_latency,
            timing_string=timing_string,
            die_type=die_type,
            memory_type=memory_type,
            form_factor=form_factor,
            has_rgb=has_rgb,
            xmp_version=xmp_version,
            expo_supported=expo_supported,
            parse_confidence=round(confidence, 2),
        )

    def _extract_die_type(self, title: str) -> str | None:
        """从标题匹配颗粒型号。"""
        title_lower = title.lower()
        for die_name, keywords in DIE_KEYWORDS.items():
            for kw in keywords:
                if kw in title_lower:
                    return die_name
        return None

    def _extract_brand(self, title: str) -> str:
        """从标题提取品牌，使用品牌归一化。"""
        title_lower = title.lower()
        for kw in SPEC_BRAND_KEYWORDS:
            if kw in title_lower:
                return brand_normalizer.normalize(kw)
        # 取标题第一段作为品牌
        first_word = title.split()[0] if title else ""
        return brand_normalizer.normalize(first_word)

    def _extract_model(self, title: str, brand: str) -> str:
        """从标题提取型号。去除品牌前缀后取前几个 token。"""
        title = title.strip()
        brand_lower = brand.lower()
        # Try removing brand from start
        for prefix in [brand, brand_lower, brand.upper()]:
            if title.lower().startswith(prefix.lower()):
                title = title[len(prefix):].strip()
                break
        # Take meaningful tokens
        tokens = title.split()
        # Skip capacity/speed tokens
        skip_pattern = re.compile(
            r"^\d+GB|DDR[45]|\d+MHz|CL\d+|RGB|ARGB|盒装|台式机|笔记本"
        )
        meaningful = [t for t in tokens[:4] if not skip_pattern.match(t)]
        return " ".join(meaningful)[:100] if meaningful else title[:100]

    @staticmethod
    def _compute_hash(raw: RawProduct) -> str:
        """计算原始数据的 SHA-256，用于去重。"""
        data = json.dumps(
            {
                "platform_code": raw.platform_code,
                "platform_sku_id": raw.platform_sku_id,
                "title": raw.title,
                "price_fen": raw.price_fen,
                "original_fen": raw.original_fen,
                "coupon_fen": raw.coupon_fen,
                "promotion_tag": raw.promotion_tag,
                "crawled_at": raw.crawled_at.isoformat(),
            },
            sort_keys=True,
        )
        return hashlib.sha256(data.encode()).hexdigest()
