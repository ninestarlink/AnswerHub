"""Shopee 渠道：客户端 / 字段映射 / Mock / 适配器。"""

from .adapter import ShopeeAdapter
from .client import ShopeeClient, build_sign
from .map import map_order, map_product, map_stock
from .mock import MockShopeeClient

__all__ = [
    "MockShopeeClient",
    "ShopeeAdapter",
    "ShopeeClient",
    "build_sign",
    "map_order",
    "map_product",
    "map_stock",
]
