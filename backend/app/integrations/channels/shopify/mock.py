"""Shopify 内置 Mock：进程内虚构数据，不依赖 development store 与网络。

结构贴近 Admin REST 的原生对象（`name / financial_status / line_items / variants`），
与真实客户端共用同一套 `map_*`。订单号沿用 Shopify 的 `#1001` 形式。

所有店铺、客户、地址均为虚构演示数据。
"""

from __future__ import annotations

from ..base import ChannelNotFound

_CATALOG: dict[str, dict] = {
    "p1001": {"name": "轻云 Pro 缓震跑鞋", "price": "99.00", "color": "蓝紫", "stock": {"40": 25, "41": 40, "42": 38, "43": 12}},
    "p1002": {"name": "疾风 2.0 碳板跑鞋", "price": "139.00", "color": "橙黑", "stock": {"40": 15, "41": 22, "42": 18, "43": 9}},
    "p1003": {"name": "烈焰 X3 实战篮球鞋", "price": "119.00", "color": "黑红", "stock": {"41": 20, "42": 26, "43": 14, "44": 8}},
    "p1004": {"name": "山野 GTX 越野跑鞋", "price": "159.00", "color": "深绿", "stock": {"41": 6, "42": 2, "43": 5}},
    "p1005": {"name": "街头 Classic 休闲板鞋", "price": "69.00", "color": "米白", "stock": {"39": 35, "40": 42, "41": 38, "42": 25}},
    "p1006": {"name": "云步 轻量健步鞋", "price": "59.00", "color": "灰色", "stock": {"39": 28, "40": 24, "41": 16, "42": 10}},
}

PRODUCTS: list[dict] = [
    {
        "id": 7000 + idx,
        "title": item["name"],
        "product_type": "SHOES",
        "currency": "SGD",
        "variants": [
            {
                "id": (7000 + idx) * 1000 + int(size),
                "title": size,
                "sku": f"SKU-{pid.upper()}-{size}",
                "price": item["price"],
                "inventory_quantity": qty,
            }
            for size, qty in item["stock"].items()
        ],
    }
    for idx, (pid, item) in enumerate(_CATALOG.items(), start=1)
]

ORDERS: dict[str, dict] = {
    "#1001": {
        "id": 5001,
        "name": "#1001",
        "order_number": 1001,
        "financial_status": "paid",
        "fulfillment_status": None,
        "cancelled_at": None,
        "currency": "SGD",
        "total_price": "139.00",
        "total_discounts": "0.00",
        "payment_gateway": "shopify_payments",
        "shipping_address": {
            "name": "Chen Wei",
            "address1": "Orchard Road 12-03",
            "city": "Singapore",
            "province": "Central",
            "zip": "238888",
            "country": "Singapore",
        },
        "created_at": "2026-10-22T02:12:00Z",
        "processed_at": "2026-10-22T02:13:00Z",
        "fulfillments": [],
        "line_items": [
            {
                "id": 9001,
                "product_id": 7002,
                "title": _CATALOG["p1002"]["name"],
                "variant_title": "42",
                "quantity": 1,
                "price": "139.00",
                "sku": "SKU-P1002-42",
            }
        ],
    },
    "#1002": {
        "id": 5002,
        "name": "#1002",
        "order_number": 1002,
        "financial_status": "paid",
        "fulfillment_status": "fulfilled",
        "cancelled_at": None,
        "currency": "SGD",
        "total_price": "69.00",
        "total_discounts": "5.00",
        "payment_gateway": "manual",
        "shipping_address": {
            "name": "Lim Mei",
            "address1": "Tampines Ave 3 #08-77",
            "city": "Singapore",
            "province": "East",
            "zip": "520123",
            "country": "Singapore",
        },
        "created_at": "2026-10-18T11:40:00Z",
        "processed_at": "2026-10-18T11:41:00Z",
        "fulfillments": [
            {
                "created_at": "2026-10-19T01:20:00Z",
                "shipment_status": "in_transit",
                "tracking_company": "DHL eCommerce",
            }
        ],
        "line_items": [
            {
                "id": 9002,
                "product_id": 7005,
                "title": _CATALOG["p1005"]["name"],
                "variant_title": "41",
                "quantity": 1,
                "price": "69.00",
                "sku": "SKU-P1005-41",
            }
        ],
    },
    "#1003": {
        "id": 5003,
        "name": "#1003",
        "order_number": 1003,
        "financial_status": "refunded",
        "fulfillment_status": "fulfilled",
        "cancelled_at": None,
        "currency": "SGD",
        "total_price": "119.00",
        "total_discounts": "0.00",
        "payment_gateway": "paypal",
        "shipping_address": {
            "name": "Arjun K.",
            "address1": "Toa Payoh Lor 2 #12-09",
            "city": "Singapore",
            "province": "Central",
            "zip": "310145",
            "country": "Singapore",
        },
        "created_at": "2026-10-05T00:30:00Z",
        "processed_at": "2026-10-05T00:31:00Z",
        "fulfillments": [
            {"created_at": "2026-10-06T03:00:00Z", "shipment_status": "delivered", "tracking_company": "Ninja Van"}
        ],
        "line_items": [
            {
                "id": 9003,
                "product_id": 7003,
                "title": _CATALOG["p1003"]["name"],
                "variant_title": "42",
                "quantity": 1,
                "price": "119.00",
                "sku": "SKU-P1003-42",
            }
        ],
    },
    "#1004": {
        "id": 5004,
        "name": "#1004",
        "order_number": 1004,
        "financial_status": "voided",
        "fulfillment_status": None,
        "cancelled_at": "2026-10-20T06:00:00Z",
        "cancel_reason": "customer",
        "currency": "SGD",
        "total_price": "59.00",
        "total_discounts": "0.00",
        "payment_gateway": "manual",
        "shipping_address": {
            "name": "Siti R.",
            "address1": "Jurong West St 42 #05-11",
            "city": "Singapore",
            "province": "West",
            "zip": "640512",
            "country": "Singapore",
        },
        "created_at": "2026-10-20T05:30:00Z",
        "processed_at": "2026-10-20T05:31:00Z",
        "fulfillments": [],
        "line_items": [
            {
                "id": 9004,
                "product_id": 7006,
                "title": _CATALOG["p1006"]["name"],
                "variant_title": "40",
                "quantity": 1,
                "price": "59.00",
                "sku": "SKU-P1006-40",
            }
        ],
    },
}

SHOP_INFO = {
    "name": "云驰运动 · Shopify 演示店",
    "domain": "yunchi-demo.myshopify.com",
    "country_name": "Singapore",
    "currency": "SGD",
}


class MockShopifyClient:
    """与 ShopifyClient 同接口，返回已经解析过的 JSON 对象。"""

    mode = "mock"

    async def get_order_raw(self, order_no: str) -> dict:
        key = (order_no or "").strip()
        if not key.startswith("#"):
            key = f"#{key}"
        raw = ORDERS.get(key)
        if raw is None:
            raise ChannelNotFound(f"Shopify 中不存在订单 {order_no}")
        return raw

    async def list_products(self, limit: int = 50) -> list[dict]:
        return PRODUCTS[: max(int(limit or 50), 1)]

    async def get_shop_info(self) -> dict:
        return SHOP_INFO

    async def probe(self) -> dict:
        return {
            "shop": SHOP_INFO["name"],
            "domain": SHOP_INFO["domain"],
            "products": len(PRODUCTS),
            "orders": len(ORDERS),
            "note": "进程内虚构数据，未触发 Admin API 请求",
        }
