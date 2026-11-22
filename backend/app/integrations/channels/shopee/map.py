"""Shopee Open API v2 字段映射：原生结构 → 项目契约。

只读接口返回的是 `{"error","message","request_id","response"}` 信封，
真正数据在 `response` 里；这里只处理 `response` 内部的对象。
"""

from __future__ import annotations

from ..base import _money, _unix_dt, empty_order, split_sku, status_text

# Shopee 订单状态 → 内部状态
SHOPEE_STATUS = {
    "UNPAID": "pending_payment",
    "READY_TO_SHIP": "paid",
    "PROCESSED": "paid",
    "SHIPPED": "shipped",
    "TO_CONFIRM_RECEIVE": "delivered",
    "COMPLETED": "completed",
    "CANCELLED": "cancelled",
    "IN_CANCEL": "cancelled",
    "TO_RETURN": "refunding",
}

# Shopee 支付方式枚举 → 展示文案
_PAY_METHOD = {
    "CREDIT_CARD": "信用卡",
    "BANK_TRANSFER": "银行转账",
    "COD": "货到付款",
    "SHOPEEPAY": "ShopeePay",
    "PAYPAL": "PayPal",
}


def map_order(raw: dict) -> dict:
    """`get_order_detail` 的单条订单 → 内部订单契约。"""
    order_no = str(raw.get("order_sn") or "").strip()
    status = SHOPEE_STATUS.get(str(raw.get("order_status") or "").upper(), "unknown")
    recipient = raw.get("recipient_address") or {}
    pay_code = str(raw.get("payment_method") or "").upper()

    order = empty_order(order_no)
    order.update(
        {
            "status": status,
            "status_text": status_text(status),
            "total_amount": _money(raw.get("total_amount")),
            "discount_amount": _money(raw.get("seller_discount")),
            "pay_method": _PAY_METHOD.get(pay_code, raw.get("payment_method")),
            "address": recipient.get("full_address"),
            "created_at": _unix_dt(raw.get("create_time")),
            "paid_at": _unix_dt(raw.get("pay_time")),
            "shipped_at": _unix_dt(raw.get("ship_time")),
            "delivered_at": _unix_dt(raw.get("deliver_time")),
            "items": [
                {
                    "product_id": split_sku(i.get("item_sku"))[0] or str(i.get("item_id") or ""),
                    "product_name": i.get("item_name"),
                    "size": i.get("model_name") or split_sku(i.get("model_sku"))[1],
                    "qty": int(i.get("model_quantity_purchased") or 0),
                    "unit_price": _money(i.get("model_discounted_price") or i.get("model_original_price")),
                }
                for i in raw.get("item_list") or []
            ],
        }
    )
    return order


def map_stock(raw: dict) -> dict:
    """商品 + 型号拼出来的一行库存 → variant 风格。"""
    item_sku = str(raw.get("item_sku") or "")
    model_sku = str(raw.get("model_sku") or "")
    product_id, size = split_sku(item_sku or model_sku)
    summary = ((raw.get("stock_info_v2") or {}).get("summary_info") or {})
    available = max(int(summary.get("total_available_stock") or 0), 0)

    return {
        "sku": model_sku or item_sku,
        "product_id": product_id,
        "size": raw.get("model_name") or size,
        "color": raw.get("color"),
        "available": available,
        "reserved": 0,
        "warehouse": raw.get("_warehouse") or "Shopee 仓",
        "low_stock": available <= 5,
    }


def map_product(raw: dict) -> dict:
    """`get_item_base_info` 的单条商品 → 商品主数据。"""
    prices = raw.get("price_info") or []
    price = prices[0] if prices else {}
    item_sku = str(raw.get("item_sku") or "")
    return {
        "product_id": split_sku(item_sku)[0] or str(raw.get("item_id") or ""),
        "name": raw.get("item_name"),
        "price": _money(price.get("current_price") or price.get("original_price")),
        "currency": price.get("currency") or "SGD",
        "category": raw.get("category") or "SHOES",
    }


def map_shop(raw: dict) -> dict:
    return {
        "shop_name": raw.get("shop_name"),
        "region": raw.get("region"),
        "status": raw.get("status"),
        "currency": raw.get("currency"),
    }


__all__ = ["SHOPEE_STATUS", "map_order", "map_product", "map_shop", "map_stock"]
