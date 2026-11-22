"""Shopify 适配器：订单 / 库存 / 商品主数据。"""

from __future__ import annotations

from ..base import ChannelNotFound, normalize_sku, split_sku
from .map import map_order, map_product, map_stock


class ShopifyAdapter:
    platform = "shopify"

    def __init__(self, client, mode: str = "mock") -> None:
        self.client = client
        self.mode = mode
        self.name = f"shopify-{mode}"

    async def get_order(self, order_no: str) -> dict:
        return map_order(await self.client.get_order_raw(order_no))

    async def get_stock(self, sku: str) -> dict:
        code = normalize_sku(sku)
        for product in await self.client.list_products(limit=250):
            product_id = split_sku((product.get("variants") or [{}])[0].get("sku") or "")[0] or str(
                product.get("id") or ""
            )
            for variant in product.get("variants") or []:
                if normalize_sku(variant.get("sku")) == code:
                    return map_stock(
                        {
                            "sku": variant.get("sku"),
                            "product_id": product_id,
                            "variant_title": variant.get("title"),
                            "inventory_quantity": variant.get("inventory_quantity"),
                            "warehouse": "Shopify 主仓",
                        }
                    )
        raise ChannelNotFound(f"Shopify 中不存在 SKU {code}")

    async def pull_master_data(self, entity: str) -> dict:
        key = (entity or "").strip().lower()
        if key not in ("products", "items"):
            raise ChannelNotFound(f"不支持的主数据实体 {entity!r}，当前仅支持 products")

        rows = await self.client.list_products(limit=50)
        return {
            "entity": "products",
            "count": len(rows),
            "items": [map_product(row) for row in rows],
        }

    async def probe(self) -> dict:
        return await self.client.probe()
