"""渠道适配层纯单元测试：签名、状态映射、SKU 归一与 Mock 适配器。"""

from __future__ import annotations

import asyncio
import unittest

from app.integrations.channels import (
    ChannelNotFound,
    normalize_sku,
    split_sku,
)
from app.integrations.channels.shopee import (
    MockShopeeClient,
    ShopeeAdapter,
    build_sign,
    map_order as map_shopee_order,
    map_stock as map_shopee_stock,
)
from app.integrations.channels.shopee.mock import ITEM_IDS, MODELS_BY_ITEM, ORDERS as SHOPEE_ORDERS
from app.integrations.channels.shopify import (
    MockShopifyClient,
    ShopifyAdapter,
    map_order as map_shopify_order,
)
from app.integrations.channels.shopify.mock import ORDERS as SHOPIFY_ORDERS
from app.integrations.channels.shopee import client as shopee_client
from app.integrations.channels.shopify.client import ShopifyClient


class PlatformEndpointTest(unittest.TestCase):
    """锁住接入的是哪套 API，避免把 Shopee / Shopify 的路径写混。"""

    def test_shopee_open_api_v2_paths(self):
        self.assertEqual(shopee_client._PATH_ORDER, "/api/v2/order/get_order_detail")
        self.assertEqual(shopee_client._PATH_ITEM_LIST, "/api/v2/product/get_item_list")
        self.assertEqual(shopee_client._PATH_ITEM_BASE, "/api/v2/product/get_item_base_info")
        self.assertEqual(shopee_client._PATH_MODELS, "/api/v2/product/get_model_list")
        self.assertEqual(shopee_client._PATH_SHOP, "/api/v2/shop/get_shop_info")

    def test_shopify_admin_rest_version(self):
        client = ShopifyClient(
            shop_domain="demo-store.myshopify.com",
            access_token="token",
            api_version="2024-10",
        )
        self.assertEqual(client.base_url, "https://demo-store.myshopify.com")
        self.assertEqual(client.admin_path, "/admin/api/2024-10")


class ShopeeSignatureTest(unittest.TestCase):
    def test_known_vector(self):
        # 公式：HMAC-SHA256(partner_key, partner_id + path + timestamp + access_token + shop_id)
        sign = build_sign(123, "secret", "/api/v2/shop/get_shop_info", 1700000000, "token", 456)
        self.assertEqual(
            sign,
            "e67c7377f945212d573a9d9656d96a69109c9ef16d5efd5ec74f51269bdccb89",
        )

    def test_deterministic(self):
        args = (123, "secret", "/api/v2/order/get_order_detail", 1700000000, "token", 456)
        self.assertEqual(build_sign(*args), build_sign(*args))


class SkuTest(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_sku("p1004-42"), "SKU-P1004-42")
        self.assertEqual(normalize_sku(" SKU-p1004-42 "), "SKU-P1004-42")
        self.assertEqual(normalize_sku(""), "")

    def test_split(self):
        self.assertEqual(split_sku("SKU-P1004-42"), ("p1004", "42"))
        self.assertEqual(split_sku("bad"), ("bad", ""))
        self.assertEqual(split_sku(""), ("", ""))


class ShopeeMapTest(unittest.TestCase):
    def test_order_mapping(self):
        order = map_shopee_order(SHOPEE_ORDERS["231022SPE002"])
        self.assertEqual(order["order_no"], "231022SPE002")
        self.assertEqual(order["status"], "shipped")
        self.assertEqual(order["status_text"], "已发货运输中")
        self.assertEqual(order["total_amount"], 69.0)
        self.assertEqual(order["pay_method"], "ShopeePay")
        self.assertEqual(order["items"][0]["product_id"], "p1005")
        self.assertEqual(order["items"][0]["size"], "41")
        # 东八区展示：2026-10-18T19:40:00+08:00
        self.assertEqual(order["created_at"], "2026-10-18 19:40")

    def test_return_maps_to_refunding(self):
        order = map_shopee_order(SHOPEE_ORDERS["231022SPE003"])
        self.assertEqual(order["status"], "refunding")

    def test_stock_mapping(self):
        base = {"item_sku": "SKU-P1004", "item_name": "山野 GTX 越野跑鞋"}
        model = MODELS_BY_ITEM[ITEM_IDS["p1004"]][0]
        row = {**base, **model, "_warehouse": "Shopee 卖家仓"}
        stock = map_shopee_stock(row)
        self.assertEqual(stock["sku"], "SKU-P1004-41")
        self.assertEqual(stock["product_id"], "p1004")
        self.assertEqual(stock["available"], 6)
        self.assertFalse(stock["low_stock"])


class ShopifyMapTest(unittest.TestCase):
    def test_status_combinations(self):
        self.assertEqual(map_shopify_order(SHOPIFY_ORDERS["#1001"])["status"], "paid")
        self.assertEqual(map_shopify_order(SHOPIFY_ORDERS["#1002"])["status"], "shipped")
        self.assertEqual(map_shopify_order(SHOPIFY_ORDERS["#1003"])["status"], "refunding")
        self.assertEqual(map_shopify_order(SHOPIFY_ORDERS["#1004"])["status"], "cancelled")

    def test_timezone_and_items(self):
        order = map_shopify_order(SHOPIFY_ORDERS["#1002"])
        # 2026-10-18T11:40:00Z → 东八区 19:40
        self.assertEqual(order["created_at"], "2026-10-18 19:40")
        self.assertEqual(order["shipped_at"], "2026-10-19 09:20")
        self.assertEqual(order["items"][0]["product_id"], "p1005")
        self.assertEqual(order["items"][0]["size"], "41")


class MockAdapterTest(unittest.TestCase):
    def test_shopee_adapter(self):
        adapter = ShopeeAdapter(MockShopeeClient())

        order = asyncio.run(adapter.get_order("231022SPE001"))
        self.assertEqual(order["status"], "paid")

        stock = asyncio.run(adapter.get_stock("SKU-P1004-42"))
        self.assertEqual(stock["available"], 2)
        self.assertTrue(stock["low_stock"])

        products = asyncio.run(adapter.pull_master_data("products"))
        self.assertEqual(products["count"], 6)
        self.assertTrue(products["items"])

        with self.assertRaises(ChannelNotFound):
            asyncio.run(adapter.get_order("NOT-EXIST"))

    def test_shopify_adapter(self):
        adapter = ShopifyAdapter(MockShopifyClient())

        order = asyncio.run(adapter.get_order("1001"))
        self.assertEqual(order["order_no"], "#1001")
        self.assertEqual(order["status"], "paid")

        stock = asyncio.run(adapter.get_stock("p1004-43"))
        self.assertEqual(stock["sku"], "SKU-P1004-43")
        self.assertEqual(stock["available"], 5)

        products = asyncio.run(adapter.pull_master_data("products"))
        self.assertEqual(products["count"], 6)

        with self.assertRaises(ChannelNotFound):
            asyncio.run(adapter.get_stock("SKU-NOPE-1"))


if __name__ == "__main__":
    unittest.main()
