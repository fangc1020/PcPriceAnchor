import hashlib
import json
import logging
import re
from decimal import Decimal
from pathlib import Path
from typing import Dict, List

import yaml

logger = logging.getLogger(__name__)


class BrandNormalizer:
    """品牌别名归一化：启动时从 YAML 加载别名表进内存。"""

    def __init__(self, aliases_path: str | None = None) -> None:
        self._alias_to_canonical: dict[str, str] = {}
        if aliases_path is None:
            aliases_path = str(
                Path(__file__).parent.parent.parent / "config" / "brand_aliases.yml"
            )
        self._load_aliases(aliases_path)

    def _load_aliases(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except (FileNotFoundError, yaml.YAMLError) as e:
            logger.warning("Failed to load brand aliases: %s", e)
            return

        for canonical, aliases in (data or {}).items():
            self._alias_to_canonical[canonical.lower()] = canonical
            for alias in aliases:
                self._alias_to_canonical[alias.lower()] = canonical

    def normalize(self, raw_brand: str) -> str:
        """将品牌名称映射到规范名称，未知品牌原样返回。"""
        if not raw_brand:
            return ""
        return self._alias_to_canonical.get(raw_brand.lower().strip(), raw_brand.strip())


# 全局单例
brand_normalizer = BrandNormalizer()
