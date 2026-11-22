"""Shopee 内置 Mock：进程内虚构数据，不依赖网络与卖家账号。

数据结构刻意贴近 Open API v2 的原生返回（`order_sn / item_list / stock_info_v2`），
再走与真实客户端相同的 `map_*`，保证「Mock 能跑」不等于「真接口对不上」。

订单号、店铺、地址均为虚构演示数据。
"""

from __future__ import annotations

from datetime import datetime

from ..base import TZ_CN, ChannelNotFound

# 商品目录：price 用 SGD 展示，贴近跨境场景；库存按尺码拆成 model
_CATALOG: dict[str, dict] = {
    "p1001": {"name": "轻云 Pro 缓震跑鞋", "price": 99.0, "color": "蓝紫", "stock": {"40": 25, "41": 40, "42": 38, "43": 12}},
    "p1002": {"name": "疾风 2.0 碳板跑鞋", "price": 139.0, "color": "橙黑", "stock": {"40": 15, "41": 22, "42": 18, "43": 9}},
    "p1003": {"name": "烈焰 X3 实战篮球鞋", "price": 119.0, "color": "黑红", "stock": {"41": 20, "42": 26, "43": 14, "44": 8}},
    "p1004": {"name": "山野 GTX 越野跑鞋", "price": 159.0, "color": "深绿", "stock": {"41": 6, "42": 2, "43": 5}},
    "p1005": {"name": "街头 Classic 休闲板鞋", "price": 69.0, "color": "米白", "stock": {"39": 35, "40": 42, "41": 38, "42": 25}},
    "p1006": {"name": "云步 轻量健步鞋", "price": 59.0, "color": "灰色", "stock": {"39": 28, "40": 24, "41": 16, "42": 10}},
}

ITEM_IDS = {pid: 9021000 + idx for idx, pid in enumerate(_CATALOG)}

# get_item_base_info 的原生结构
ITEM_BASE: list[dict] = [
    {
        "item_id": ITEM_IDS[pid],
        "item_name": item["name"],
        "item_sku": f"SKU-{pid.upper()}",
        "item_status": "NORMAL",
        "category": "SHOES",
        "price_info": [{"currency": "SGD", "original_price": item["price"], "current_price": item["price"]}],
    }
    for pid, item in _CATALOG.items()
]

# get_model_list 的原生结构，一个尺码一个 model
MODELS_BY_ITEM: dict[int, list[dict]] = {
    ITEM_IDS[pid]: [
        {
            "model_id": int(f"{ITEM_IDS[pid]}{size}"),
            "model_name": size,
            "model_sku": f"SKU-{pid.upper()}-{size}",
            "stock_info_v2": {"summary_info": {"total_available_stock": qty}},
        }
        for size, qty in item["stock"].items()
    ]
    for pid, item in _CATALOG.items()
}


def _ts(text: str) -> int:
    """固定东八区解释时间，避免不同机器时区导致 fixtures 漂移。"""
    return int(datetime.fromisoformat(text).replace(tzinfo=TZ_CN).timestamp())


ORDERS: dict[str, dict] = {
    "231022SPE001": {
        "order_sn": "231022SPE001",
        "order_status": "READY_TO_SHIP",
        "currency": "SGD",
        "total_amount": 139.0,
        "seller_discount": 0.0,
        "payment_method": "CREDIT_CARD",
        "recipient_address": {"name": "Chen Wei", "phone": "+65 **** 8821", "full_address": "Singapore 238888, Orchard Road 12-03"},
        "create_time": _ts("2026-10-22T10:12:00"),
        "pay_time": _ts("2026-10-22T10:13:00"),
        "ship_time": 0,
        "deliver_time": 0,
        "item_list": [
            {
                "item_id": ITEM_IDS["p1002"],
                "item_name": _CATALOG["p1002"]["name"],
                "item_sku": "SKU-P1002",
                "model_sku": "SKU-P1002-42",
                "model_name": "42",
                "model_quantity_purchased": 1,
                "model_discounted_price": 139.0,
            }
        ],
    },
    "231022SPE002": {
        "order_sn": "231022SPE002",
        "order_status": "SHIPPED",
        "currency": "SGD",
        "total_amount": 69.0,
        "seller_discount": 5.0,
        "payment_method": "SHOPEEPAY",
        "recipient_address": {"name": "Lim Mei", "phone": "+65 **** 3310", "full_address": "Singapore 520123, Tampines Ave 3 #08-77"},
        "create_time": _ts("2026-10-18T19:40:00"),
        "pay_time": _ts("2026-10-18T19:41:00"),
        "ship_time": _ts("2026-10-19T09:20:00"),
        "deliver_time": 0,
        "item_list": [
            {
                "item_id": ITEM_IDS["p1005"],
                "item_name": _CATALOG["p1005"]["name"],
                "item_sku": "SKU-P1005",
                "model_sku": "SKU-P1005-41",
                "model_name": "41",
                "model_quantity_purchased": 1,
                "model_discounted_price": 69.0,
            }
        ],
    },
    "231022SPE003": {
        "order_sn": "231022SPE003",
        "order_status": "TO_RETURN",
        "currency": "SGD",
        "total_amount": 119.0,
        "seller_discount": 0.0,
        "payment_method": "BANK_TRANSFER",
        "recipient_address": {"name": "Arjun K.", "phone": "+65 **** 5088", "full_address": "Singapore 310145, Toa Payoh Lor 2 #12-09"},
        "create_time": _ts("2026-10-05T08:30:00"),
        "pay_time": _ts("2026-10-05T08:31:00"),
        "ship_time": _ts("2026-10-06T11:00:00"),
        "deliver_time": _ts("2026-10-09T15:45:00"),
        "item_list": [
            {
                "item_id": ITEM_IDS["p1003"],
                "item_name": _CATALOG["p1003"]["name"],
                "item_sku": "SKU-P1003",
                "model_sku": "SKU-P1003-42",
                "model_name": "42",
                "model_quantity_purchased": 1,
                "model_discounted_price": 119.0,
            }
        ],
    },
}

SHOP_INFO = {
    "shop_name": "云驰运动 · Shopee 演示店",
    "region": "SG",
    "status": "NORMAL",
    "currency": "SGD",
}


class MockShopeeClient:
    """与 ShopeeClient 同接口，返回已经解包过的 `response` 内容。"""

    mode = "mock"

    async def get_order_raw(self, order_no: str) -> dict:
        raw = ORDERS.get((order_no or "").strip())
        if raw is None:
            raise ChannelNotFound(f"Shopee 中不存在订单 {order_no}")
        return raw

    async def list_items(self, offset: int = 0, page_size: int = 50) -> dict:
        end = offset + page_size
        rows = ITEM_BASE[offset:end]
        return {
            "item": rows,
            "has_next_page": end < len(ITEM_BASE),
            "next_offset": end,
        }

    async def get_item_base_info(self, item_ids: list[int]) -> list[dict]:
        wanted = {int(i) for i in item_ids}
        return [row for row in ITEM_BASE if row["item_id"] in wanted]

    async def get_model_list(self, item_id: int) -> list[dict]:
        return MODELS_BY_ITEM.get(int(item_id), [])

    async def get_shop_info(self) -> dict:
        return SHOP_INFO

    async def probe(self) -> dict:
        return {
            "shop": SHOP_INFO["shop_name"],
            "items": len(ITEM_BASE),
            "orders": len(ORDERS),
            "note": "进程内虚构数据，未触发签名与网络请求",
        }
