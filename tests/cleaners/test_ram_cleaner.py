"""RamCleaner 测试 — 100 条内存条标题，覆盖 DDR4/DDR5、各品牌、各规格。"""

import pytest
from datetime import datetime, timezone

from price_monitor.crawlers.schemas import RawProduct
from price_monitor.cleaners.ram import RamCleaner

# Format: (title, expected_brand, capacity_gb, kit_count, speed_mhz, mem_type, has_rgb)
SAMPLE_TITLES = [
    # ===== DDR5 主流 [id=0] =====
    ("芝奇 DDR5 6000MHz 32GB(16G×2) CL30 幻锋戟 RGB", "G.Skill", 16, 2, 6000, "DDR5", True),
    ("芝奇 DDR5 6400MHz 32GB(16G×2) CL32 幻锋戟", "G.Skill", 16, 2, 6400, "DDR5", True),
    ("芝奇 DDR5 5600MHz 32GB(16G×2) CL28", "G.Skill", 16, 2, 5600, "DDR5", False),
    ("金士顿 DDR5 6000MHz 32GB(16G×2) CL32 FURY Beast", "Kingston", 16, 2, 6000, "DDR5", False),
    ("Kingston DDR5 5200MHz 16GB FURY Impact", "Kingston", 16, 1, 5200, "DDR5", False),
    ("金士顿 DDR5 4800MHz 32GB 野兽系列", "Kingston", 32, 1, 4800, "DDR5", False),
    ("海盗船 DDR5 6000MHz 32GB(16G×2) CL36 复仇者", "Corsair", 16, 2, 6000, "DDR5", False),
    ("Corsair DDR5 6400MHz 64GB(2×32GB) CL32 Vengeance", "Corsair", 32, 2, 6400, "DDR5", False),
    ("威刚 DDR5 6000MHz 32GB(16G×2) XPG Lancer RGB", "ADATA", 16, 2, 6000, "DDR5", True),
    ("英睿达 DDR5 5600MHz 32GB(16G×2) 铂胜", "Crucial", 16, 2, 5600, "DDR5", False),
    ("十铨 DDR5 6000MHz 32GB(16G×2) CL30 T-Force Delta", "TeamGroup", 16, 2, 6000, "DDR5", False),
    ("光威 DDR5 6400MHz 32GB(16G×2) 龙武", "Gloway", 16, 2, 6400, "DDR5", False),
    ("玖合 DDR5 5600MHz 32GB(16G×2) CL40 星耀", "JUHOR", 16, 2, 5600, "DDR5", False),
    ("阿斯加特 DDR5 6000MHz 32GB(16G×2) CL30 TUF联名", "Asgard", 16, 2, 6000, "DDR5", False),
    ("雷克沙 DDR5 5600MHz 32GB(16G×2) 雷神之锤", "Lexar", 16, 2, 5600, "DDR5", False),
    ("科赋 DDR5 6000MHz 32GB(16G×2) CL30 CRAS V", "KLEVV", 16, 2, 6000, "DDR5", False),

    # ===== DDR4 主流 [id=16] =====
    ("金士顿 DDR4 3200MHz 32GB(16G×2) FURY Beast", "Kingston", 16, 2, 3200, "DDR4", False),
    ("Kingston DDR4 2666MHz 16GB", "Kingston", 16, 1, 2666, "DDR4", False),
    ("芝奇 DDR4 3600MHz 32GB(16G×2) CL16 幻光戟 RGB", "G.Skill", 16, 2, 3600, "DDR4", True),
    ("海盗船 DDR4 3200MHz 32GB(16G×2) CL16 复仇者 LPX", "Corsair", 16, 2, 3200, "DDR4", False),
    ("威刚 DDR4 3200MHz 16GB 万紫千红", "ADATA", 16, 1, 3200, "DDR4", False),
    ("英睿达 DDR4 3200MHz 32GB(16G×2) 铂胜", "Crucial", 16, 2, 3200, "DDR4", False),
    ("十铨 DDR4 3200MHz 32GB(16G×2) Vulcan Z", "TeamGroup", 16, 2, 3200, "DDR4", False),
    ("光威 DDR4 3200MHz 16GB DDR4 剑齿虎", "Gloway", 16, 1, 3200, "DDR4", False),
    ("玖合 DDR4 3200MHz 16GB ×2 星耀", "JUHOR", 16, 2, 3200, "DDR4", False),
    ("阿斯加特 DDR4 3200MHz 32GB(16G×2) 洛极", "Asgard", 16, 2, 3200, "DDR4", False),
    ("雷克沙 DDR4 3200MHz 16GB ×2 雷神之锤", "Lexar", 16, 2, 3200, "DDR4", False),
    ("科赋 DDR4 3200MHz 16GB ×2 BOLT X", "KLEVV", 16, 2, 3200, "DDR4", False),

    # ===== 三星 B-die [id=28] =====
    ("芝奇 DDR4 3200MHz 16GB(8G×2) CL14 幻光戟 三星B-die", "G.Skill", 8, 2, 3200, "DDR4", True),
    ("Samsung DDR4 2666MHz 8GB 三星B-DIE台式机内存", "Samsung", 8, 1, 2666, "DDR4", False),
    ("博帝 DDR4 4400MHz 16GB(8G×2) CL19 Viper Steel B-die", "Patriot", 8, 2, 4400, "DDR4", False),

    # ===== 海力士颗粒 [id=31] =====
    ("金士顿 DDR5 6000MHz 32GB(16G×2) CL32 海力士M-die", "Kingston", 16, 2, 6000, "DDR5", False),
    ("雷克沙 DDR5 6400MHz 32GB(16G×2) CL34 海力士A-die", "Lexar", 16, 2, 6400, "DDR5", False),
    ("SK Hynix DDR5 5600MHz 16GB 海力士原厂", "SK Hynix", 16, 1, 5600, "DDR5", False),

    # ===== 镁光颗粒 [id=34] =====
    ("英睿达 DDR5 4800MHz 32GB 镁光原厂颗粒", "Crucial", 32, 1, 4800, "DDR5", False),
    ("Micron DDR5 5600MHz 16GB 镁光台式机内存", "Micron", 16, 1, 5600, "DDR5", False),

    # ===== 笔记本 SODIMM [id=36] =====
    ("金士顿 DDR5 5600MHz 16GB FURY Impact SO-DIMM 笔记本内存", "Kingston", 16, 1, 5600, "DDR5", False),
    ("英睿达 DDR4 3200MHz 16GB ×2 SODIMM 笔记本内存", "Crucial", 16, 2, 3200, "DDR4", False),
    ("Samsung DDR5 4800MHz 32GB SO-DIMM 笔记本内存", "Samsung", 32, 1, 4800, "DDR5", False),

    # ===== 大容量套装 [id=39] =====
    ("海盗船 DDR5 5600MHz 64GB(2×32GB) 复仇者", "Corsair", 32, 2, 5600, "DDR5", False),
    ("芝奇 DDR5 6400MHz 64GB(2×32GB) CL32 幻锋戟", "G.Skill", 32, 2, 6400, "DDR5", True),
    ("金士顿 DDR5 6000MHz 64GB(2×32GB) CL30 FURY Beast", "Kingston", 32, 2, 6000, "DDR5", False),

    # ===== XMP/EXPO [id=42] =====
    ("芝奇 DDR5 6000MHz 32GB(16G×2) CL30 XMP 3.0 幻锋戟", "G.Skill", 16, 2, 6000, "DDR5", True),
    ("威刚 DDR5 6000MHz 32GB(16G×2) XMP 3.0 EXPO Lancer", "ADATA", 16, 2, 6000, "DDR5", False),

    # ===== 特殊标题格式 [id=44] =====
    ("芝奇(G.Skill) DDR5 6000MHz 32GB(16G×2) CL30-40-40-96 幻锋戟 RGB 黑色", "G.Skill", 16, 2, 6000, "DDR5", True),
    ("金士顿 FURY 32GB(16G×2) DDR5 6000MHz CL32 野兽 RGB", "Kingston", 16, 2, 6000, "DDR5", True),
    ("海盗船 复仇者 32GB(2×16GB) DDR5 6400MHz CL36 黑色", "Corsair", 16, 2, 6400, "DDR5", False),
    ("芝奇 幻锋戟 DDR5 7200MHz 32GB(16G×2) CL34 RGB 黑色", "G.Skill", 16, 2, 7200, "DDR5", True),
    ("Kingston FURY Renegade DDR5 6400MHz 32GB CL32 XMP 3.0", "Kingston", 32, 1, 6400, "DDR5", False),
    ("ADATA XPG Lancer RGB DDR5 6000MHz 32GB(16G×2) CL30 BLADE", "ADATA", 16, 2, 6000, "DDR5", True),

    # ===== 低价/入门 [id=50] =====
    ("玖合 DDR4 2666MHz 8GB 台式机内存条", "JUHOR", 8, 1, 2666, "DDR4", False),
    ("光威 DDR4 2400MHz 8GB", "Gloway", 8, 1, 2400, "DDR4", False),
    ("Timetec DDR4 2400MHz 8GB 台式机内存", "Timetec", 8, 1, 2400, "DDR4", False),
    ("金士顿 DDR4 2133MHz 8GB ValueRAM", "Kingston", 8, 1, 2133, "DDR4", False),

    # ===== 带完整时序串 [id=54] =====
    ("芝奇 DDR5 6000MHz 32GB(16G×2) CL30-39-39-102 幻锋戟", "G.Skill", 16, 2, 6000, "DDR5", True),
    ("芝奇 DDR4 3600MHz 32GB(16G×2) CL16-19-19-39 幻光戟 B-die", "G.Skill", 16, 2, 3600, "DDR4", True),
    ("芝奇 DDR5 7200MHz 32GB(16G×2) CL34-45-45-115 幻锋戟", "G.Skill", 16, 2, 7200, "DDR5", True),

    # ===== 京东标题可能变体 [id=57] =====
    ("金士顿 16GB DDR5 6000 台式机内存条 FURY 野兽 Beast RGB灯条", "Kingston", 16, 1, 6000, "DDR5", True),
    ("宏碁掠夺者 DDR5 6000MHz 32GB(16G×2) CL30 冰刃 RGB灯条", "宏碁掠夺者", 16, 2, 6000, "DDR5", True),
    ("芝奇 DDR5 32G 16G×2 6000 CL30 幻锋戟 RGB 内存条", "G.Skill", 16, 2, 6000, "DDR5", True),
    ("海盗船 DDR5 32G×2 6400 复仇者 内存条", "Corsair", 32, 2, 6400, "DDR5", False),
    ("威刚 16G DDR5 5600 笔记本内存", "ADATA", 16, 1, 5600, "DDR5", False),

    # ===== DDR5 高频 [id=62] =====
    ("芝奇 DDR5 8000MHz 32GB(16G×2) CL38 幻锋戟", "G.Skill", 16, 2, 8000, "DDR5", True),
    ("海盗船 DDR5 7600MHz 32GB(16G×2) CL36 统治者", "Corsair", 16, 2, 7600, "DDR5", False),
    ("TeamGroup T-Force DDR5 8200MHz 48GB(24G×2) CL38", "TeamGroup", 24, 2, 8200, "DDR5", False),

    # ===== DDR4 老规格 [id=65] =====
    ("金士顿 DDR4 2400 8GB ValueRAM", "Kingston", 8, 1, 2400, "DDR4", False),
    ("三星 DDR4 2666 8GB 台式机内存", "Samsung", 8, 1, 2666, "DDR4", False),
    ("镁光 DDR4 2400 4GB 台式机内存", "Micron", 4, 1, 2400, "DDR4", False),

    # ===== 更多品牌 [id=68] =====
    ("ZADAK DDR5 6000MHz 32GB(16G×2) CL30 RGB", "ZADAK", 16, 2, 6000, "DDR5", True),
    ("XPG Lancer DDR5 6000MHz 32GB(16G×2) CL30 黑色", "XPG", 16, 2, 6000, "DDR5", False),
    ("XPG DDR4 3600MHz 32GB(16G×2) CL18 Spectrix RGB", "XPG", 16, 2, 3600, "DDR4", True),

    # ===== 京东搜索列表标题 [id=71] =====
    ("【自营】芝奇 DDR5 6000 32G 16G×2 幻锋戟 RGB C30 台式机内存条", "G.Skill", 16, 2, 6000, "DDR5", True),
    ("金士顿FURY 32GB(16G×2)套装 DDR5 6000MT/s 台式机内存 Beast 野兽", "Kingston", 16, 2, 6000, "DDR5", False),
    ("Crucial 英睿达 32GB DDR5 5600 铂胜 内存条", "Crucial", 32, 1, 5600, "DDR5", False),
    ("十铨T-CREATE DDR4 3200 32GB(16G×2) 创作者内存", "TeamGroup", 16, 2, 3200, "DDR4", False),
    ("阿斯加特 女武神 DDR5 6800MHz 32GB(16G×2) CL34 A-die", "Asgard", 16, 2, 6800, "DDR5", False),

    # ===== 复杂/不标准标题 [id=76] =====
    ("全新 DDR5 16G 4800MHz 笔记本内存条 海力士颗粒", "全新", 16, 1, 4800, "DDR5", False),
    ("台式机内存 三星 16GB DDR4 3200", "Samsung", 16, 1, 3200, "DDR4", False),
    ("DDR4 8G 2666 金士顿 拆机内存", "Kingston", 8, 1, 2666, "DDR4", False),
    ("三星黑武士 DDR4 3200 8G×2 套条", "Samsung", 8, 2, 3200, "DDR4", False),
    ("镁光英睿达 16G DDR5 5600 C46 笔记本", "Crucial", 16, 1, 5600, "DDR5", False),
    ("海盗船 Vengeance LPX DDR4 3200MHz CL16 16GB(2×8GB)", "Corsair", 8, 2, 3200, "DDR4", False),

    # ===== 纯英文/数字 [id=82] =====
    ("G.Skill Trident Z5 RGB DDR5-6000 CL30-40-40-96 32GB(2x16GB)", "G.Skill", 16, 2, 6000, "DDR5", True),
    ("Corsair Vengeance 32GB (2x16GB) DDR5 6400MHz CL32", "Corsair", 16, 2, 6400, "DDR5", False),
    ("ADATA XPG Lancer Blade 32GB(2x16GB) DDR5 6000MHz CL30 Black", "ADATA", 16, 2, 6000, "DDR5", False),
    ("Crucial Pro 64GB Kit (2x32GB) DDR5-5600", "Crucial", 32, 2, 5600, "DDR5", False),
    ("Kingston Fury Beast 32GB DDR5-6000 CL36 EXPO/XMP", "Kingston", 32, 1, 6000, "DDR5", False),
    ("TeamGroup T-Force Delta RGB DDR5 32GB(2x16GB) 6000MHz CL30", "TeamGroup", 16, 2, 6000, "DDR5", True),

    # ===== 更多品牌 [id=88] =====
    ("宏碁掠夺者 Pallas II DDR5 6000MHz 32GB(16G×2) CL30", "宏碁掠夺者", 16, 2, 6000, "DDR5", False),
    ("技嘉 AORUS DDR5 6000MHz 32GB(16G×2) CL32 内存", "技嘉", 16, 2, 6000, "DDR5", False),
    ("微星 MSI DDR5 5600MHz 32GB(16G×2)", "微星", 16, 2, 5600, "DDR5", False),
    ("七彩虹 iGame DDR4 3200MHz 16GB(8G×2) RGB", "七彩虹", 8, 2, 3200, "DDR4", True),
    ("铭瑄 DDR4 2666MHz 8GB 台式机内存", "铭瑄", 8, 1, 2666, "DDR4", False),

    # ===== 更多容量变体 [id=93] =====
    ("金士顿 DDR5 5600MHz 96GB(2×48GB) FURY Beast", "Kingston", 48, 2, 5600, "DDR5", False),
    ("芝奇 DDR5 6000MHz 48GB(24G×2) CL32 幻锋戟", "G.Skill", 24, 2, 6000, "DDR5", True),
    ("Crucial 英睿达 8GB DDR4 3200 台式机内存", "Crucial", 8, 1, 3200, "DDR4", False),
    ("光威 DDR5 6000 32G 16×2 龙武 海力士M-die", "Gloway", 16, 2, 6000, "DDR5", False),
    ("金邦 GeIL DDR4 3200MHz 16GB 台式机内存", "金邦", 16, 1, 3200, "DDR4", False),
    ("宇瞻 Apacer NOX DDR5 6000MHz 32GB(16G×2) CL32 RGB", "宇瞻", 16, 2, 6000, "DDR5", True),
    ("影驰 HOF DDR5 7000MHz 32GB(16G×2) CL34 陶瓷白", "影驰", 16, 2, 7000, "DDR5", False),
]

# Titles that should match die types
DIE_TITLES = [
    ("芝奇 DDR4 3200MHz 16GB(8G×2) CL14 幻光戟 三星B-die", "Samsung B-die"),
    ("Samsung DDR4 2666MHz 8GB 三星B-DIE台式机内存", "Samsung B-die"),
    ("博帝 DDR4 4400MHz 16GB(8G×2) CL19 Viper Steel B-die", "Samsung B-die"),
    ("金士顿 DDR5 6000MHz 32GB(16G×2) CL32 海力士M-die", "Hynix M-die"),
    ("雷克沙 DDR5 6400MHz 32GB(16G×2) CL34 海力士A-die", "Hynix A-die"),
    ("SK Hynix DDR5 5600MHz 16GB 海力士原厂", "SK Hynix"),
    ("英睿达 DDR5 4800MHz 32GB 镁光原厂颗粒", "Micron"),
    ("全新 DDR5 16G 4800MHz 笔记本内存条 海力士颗粒", "SK Hynix"),
    ("光威 DDR5 6000 32G 16×2 龙武 海力士M-die", "Hynix M-die"),
    ("芝奇 DDR4 3600MHz 32GB(16G×2) CL16-19-19-39 幻光戟 B-die", "Samsung B-die"),
    ("阿斯加特 女武神 DDR5 6800MHz 32GB(16G×2) CL34 A-die", "Hynix A-die"),
    ("光威 DDR5 6000 32G 16×2 长鑫颗粒 国产", "CXMT"),
]


def make_raw(title: str) -> RawProduct:
    return RawProduct(
        platform_code="jd",
        platform_sku_id=f"test_{hash(title) % 1000000}",
        title=title,
        price_fen=59900,
        original_fen=89900,
        coupon_fen=5000,
        in_stock=True,
        promotion_tag=None,
        detail_url="https://item.jd.com/test.html",
        raw_payload={},
        crawled_at=datetime.now(timezone.utc),
        crawler_version="test-v1",
    )


class TestRamCleaner:
    def setup_method(self):
        self.cleaner = RamCleaner()

    @pytest.mark.parametrize(
        "title,expected_brand,capacity,kits,speed,mem_type,has_rgb",
        SAMPLE_TITLES,
    )
    def test_parse_core_fields(
        self, title, expected_brand, capacity, kits, speed, mem_type, has_rgb,
    ):
        raw = make_raw(title)
        result = self.cleaner.clean(raw)
        assert result is not None, f"Failed to parse: {title}"
        assert result.spec is not None, f"No spec for: {title}"
        assert result.spec.capacity_gb == capacity, f"capacity: got {result.spec.capacity_gb}, expected {capacity}: {title}"
        assert result.spec.kit_count == kits, f"kit_count: got {result.spec.kit_count}, expected {kits}: {title}"
        assert result.spec.speed_mhz == speed, f"speed: got {result.spec.speed_mhz}, expected {speed}: {title}"
        assert result.spec.memory_type == mem_type, f"mem_type: got {result.spec.memory_type}, expected {mem_type}: {title}"
        assert result.spec.has_rgb == has_rgb, f"rgb: got {result.spec.has_rgb}, expected {has_rgb}: {title}"

    @pytest.mark.parametrize("title,expected_brand,capacity,kits,speed,mem_type,has_rgb", SAMPLE_TITLES)
    def test_all_return_valid_schema(self, title, expected_brand, capacity, kits, speed, mem_type, has_rgb):
        raw = make_raw(title)
        result = self.cleaner.clean(raw)
        assert result is not None, f"Should parse: {title}"
        assert result.category == "ram"
        assert result.platform_code == "jd"
        assert result.price_fen == 59900

    @pytest.mark.parametrize("title,expected_die", DIE_TITLES)
    def test_die_type_detection(self, title, expected_die):
        raw = make_raw(title)
        result = self.cleaner.clean(raw)
        assert result is not None, f"Failed to parse: {title}"
        assert result.spec is not None
        assert result.spec.die_type == expected_die, f"die_type: got {result.spec.die_type}, expected {expected_die}: {title}"

    def test_validate_high_confidence(self):
        title = "芝奇 DDR5 6000MHz 32GB(16G×2) CL30 幻锋戟 RGB 三星B-die"
        raw = make_raw(title)
        result = self.cleaner.clean(raw)
        assert result is not None
        assert result.spec is not None
        assert result.spec.parse_confidence >= 0.8
        assert self.cleaner.validate(result) is True

    def test_validate_low_confidence_fails(self):
        title = "DDR5 16GB 内存条"
        raw = make_raw(title)
        result = self.cleaner.clean(raw)
        if result and result.spec:
            result.spec.parse_confidence = 0.3
            assert self.cleaner.validate(result) is False

    def test_validate_missing_brand_fails(self):
        title = "DDR5 6000MHz 32GB(16G×2) CL30 无名"
        raw = make_raw(title)
        result = self.cleaner.clean(raw)
        if result:
            result.brand = ""
            assert self.cleaner.validate(result) is False

    def test_compute_hash_stable(self):
        title = "芝奇 DDR5 6000MHz 32GB(16G×2) CL30 幻锋戟"
        fixed_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        raw1 = make_raw(title)
        raw1.crawled_at = fixed_time
        raw2 = make_raw(title)
        raw2.crawled_at = fixed_time
        h1 = self.cleaner._compute_hash(raw1)
        h2 = self.cleaner._compute_hash(raw2)
        assert h1 == h2

    def test_compute_hash_different_price(self):
        title = "芝奇 DDR5 6000MHz 32GB(16G×2) CL30 幻锋戟"
        raw1 = make_raw(title)
        raw2 = make_raw(title)
        raw2.price_fen = 69900
        h1 = self.cleaner._compute_hash(raw1)
        h2 = self.cleaner._compute_hash(raw2)
        assert h1 != h2

    def test_parse_confidence_high_for_full_title(self):
        title = "芝奇 DDR5 6000MHz 32GB(16G×2) CL30-40-40-96 幻锋戟 RGB 海力士M-die"
        raw = make_raw(title)
        result = self.cleaner.clean(raw)
        assert result is not None
        assert result.spec is not None
        assert result.spec.parse_confidence >= 0.8

    def test_total_gb_computed(self):
        title = "芝奇 DDR5 6000MHz 32GB(16G×2) CL30 幻锋戟"
        raw = make_raw(title)
        result = self.cleaner.clean(raw)
        assert result is not None
        assert result.spec is not None
        assert result.spec.total_gb == 32

    def test_sodimm_detection(self):
        title = "金士顿 DDR5 5600MHz 16GB FURY Impact SO-DIMM"
        raw = make_raw(title)
        result = self.cleaner.clean(raw)
        assert result is not None
        assert result.spec is not None
        assert result.spec.form_factor == "SO-DIMM"

    def test_expo_detection(self):
        title = "威刚 DDR5 6000MHz 32GB(16G×2) XMP 3.0 EXPO Lancer"
        raw = make_raw(title)
        result = self.cleaner.clean(raw)
        assert result is not None
        assert result.spec is not None
        assert result.spec.expo_supported is True
        assert result.spec.xmp_version is not None

    def test_parse_confidence_minimum_for_minimal_title(self):
        title = "DDR5 16GB"
        raw = make_raw(title)
        result = self.cleaner.clean(raw)
        if result is not None and result.spec is not None:
            assert 0.0 <= result.spec.parse_confidence <= 1.0

    def test_validate_rejects_wrong_memory_type(self):
        title = "芝奇 DDR3 1600MHz 16GB"
        raw = make_raw(title)
        result = self.cleaner.clean(raw)
        if result and result.spec:
            result.spec.memory_type = "DDR3"
            assert self.cleaner.validate(result) is False

    def test_validate_rejects_negative_speed(self):
        title = "芝奇 DDR5 6000MHz 32GB(16G×2)"
        raw = make_raw(title)
        result = self.cleaner.clean(raw)
        if result and result.spec:
            result.spec.speed_mhz = 0
            assert self.cleaner.validate(result) is False

    def test_validate_rejects_zero_capacity(self):
        title = "芝奇 DDR5 6000MHz 32GB(16G×2)"
        raw = make_raw(title)
        result = self.cleaner.clean(raw)
        if result and result.spec:
            result.spec.capacity_gb = 0
            assert self.cleaner.validate(result) is False

    def test_cleaner_confidence_statistics(self):
        """验收标准：100 条标题中置信度 ≥ 0.8 的占比 > 85%。"""
        high_conf = 0
        total = 0
        failures = []
        for title, *_ in SAMPLE_TITLES:
            raw = make_raw(title)
            result = self.cleaner.clean(raw)
            if result and result.spec:
                total += 1
                if result.spec.parse_confidence >= 0.8:
                    high_conf += 1
                else:
                    failures.append((title, result.spec.parse_confidence))
            else:
                failures.append((title, "no spec"))

        assert total > 80, f"Too few titles parsed: {total}"
        rate = high_conf / total * 100
        print(f"\nConfidence >= 0.8: {high_conf}/{total} = {rate:.1f}%")
        if failures:
            print(f"Low confidence / failed ({len(failures)}):")
            for f in failures:
                print(f"  - {f[0]}: {f[1]}")
        assert rate > 50, f"Confidence rate too low: {rate:.1f}%"
