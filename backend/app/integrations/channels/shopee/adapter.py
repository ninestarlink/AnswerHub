"""Shopee 适配器：把客户端原生结果映射成项目契约。"""

from __future__ import annotations

from ..base import ChannelNotFound, normalize_sku
from .map import map_order, map_product, map_stock


class ShopeeAdapter:
    platform = "shopee"

    def __init__(self, client, mode: str = "mock") -> None:
        self.client = client
        self.mode = mode
        self.name = f"shopee-{mode}"

    async def get_order(self, order_no: str) -> dict:
        return map_order(await self.client.get_order_raw(order_no))

    async def _find_model(self, code: str) -> dict:
        """按 model_sku 定位库存行；Shopee 没有「按 SKU 查库存」的直连接口。"""
        offset = 0
        for _ in range(3):  # 最多翻 3 页，避免异常店铺把请求打爆
            page = await self.client.list_items(offset=offset, page_size=50)
            rows = page.get("item") or []
            item_ids = [row.get("item_id") for row in rows if row.get("item_id") is not None]
            if item_ids:
                bases = await self.client.get_item_base_info(item_ids)
                for base in bases:
                    models = await self.client.get_model_list(base.get("item_id"))
                    for model in models:
                        if normalize_sku(model.get("model_sku")) == code:
                            return {**base, **model, "_warehouse": "Shopee 卖家仓"}
            if not page.get("has_next_page"):
                break
            offset = int(page.get("next_offset") or 0)
        raise ChannelNotFound(f"Shopee 中不存在 SKU {code}")

    async def get_stock(self, sku: str) -> dict:
        return map_stock(await self._find_model(normalize_sku(sku)))

    async def pull_master_data(self, entity: str) -> dict:
        key = (entity or "").strip().lower()
        if key not in ("products", "items"):
            raise ChannelNotFound(f"不支持的主数据实体 {entity!r}，当前仅支持 products")

        offset = 0
        bases: list[dict] = []
        for _ in range(3):
            page = await self.client.list_items(offset=offset, page_size=50)
            item_ids = [
                row.get("item_id")
                for row in page.get("item") or []
                if row.get("item_id") is not None
            ]
            if item_ids:
                bases.extend(await self.client.get_item_base_info(item_ids))
            if not page.get("has_next_page"):
                break
            offset = int(page.get("next_offset") or 0)

        return {
            "entity": "products",
            "count": len(bases),
            "items": [map_product(row) for row in bases],
        }

    async def probe(self) -> dict:
        return await self.client.probe()
