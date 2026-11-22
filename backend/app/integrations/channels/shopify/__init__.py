"""Shopify 渠道：客户端 / 字段映射 / Mock / 适配器。"""

from .adapter import ShopifyAdapter
from .client import ShopifyClient
from .map import map_order, map_product, map_stock
from .mock import MockShopifyClient

__all__ = [
    "MockShopifyClient",
    "ShopifyAdapter",
    "ShopifyClient",
    "map_order",
    "map_product",
    "map_stock",
]
