"""Shopify Admin API 字段映射：原生结构 → 项目契约。

Shopify 的订单状态不像单一平台状态字段那样简单，而是
`financial_status`（支付）+ `fulfillment_status`（履约）+ `cancelled_at` 三者组合，
映射时必须一起看，否则会把「已退款但已发货」错判成「已发货」。
"""

from __future__ import annotations

from ..base import _iso_dt, _money, empty_order, split_sku, status_text

_PAY_METHOD = {
    "shopify_payments": "Shopify Payments",
    "manual": "手动支付",
    "cash_on_delivery": "货到付款",
    "paypal": "PayPal",
    "stripe": "Stripe",
}


def _status(raw: dict) -> str:
    financial = str(raw.get("financial_status") or "").lower()
    fulfillment = str(raw.get("fulfillment_status") or "").lower()

    if raw.get("cancelled_at") or financial in ("voided", "expired"):
        return "cancelled"
    if financial in ("refunded", "partially_refunded"):
        return "refunding"
    if fulfillment == "fulfilled":
        return "shipped"
    if financial == "paid":
        return "paid"
    if financial in ("pending", "authorized", "partially_paid"):
        return "pending_payment"
    return "unknown"


def _address(raw: dict | None) -> str | None:
    if not raw:
        return None
    parts = [
        raw.get("address1"),
        raw.get("address2"),
        raw.get("city"),
        raw.get("province"),
        raw.get("zip"),
        raw.get("country"),
    ]
    text = ", ".join(str(p).strip() for p in parts if str(p or "").strip())
    return text or None


def _shipped_at(raw: dict) -> str | None:
    fulfillments = raw.get("fulfillments") or []
    if not fulfillments:
        return None
    created = sorted(str(f.get("created_at") or "") for f in fulfillments)
    return _iso_dt(created[0]) if created and created[0] else None


def map_order(raw: dict) -> dict:
    order_no = str(raw.get("name") or raw.get("id") or "").strip()
    status = _status(raw)

    order = empty_order(order_no)
    order.update(
        {
            "status": status,
            "status_text": status_text(status),
            "total_amount": _money(raw.get("total_price")),
            "discount_amount": _money(raw.get("total_discounts")),
            "pay_method": _PAY_METHOD.get(
                str(raw.get("payment_gateway") or "").lower(),
                raw.get("payment_gateway"),
            ),
            "address": _address(raw.get("shipping_address")),
            "created_at": _iso_dt(raw.get("created_at")),
            "paid_at": _iso_dt(raw.get("processed_at")),
            "shipped_at": _shipped_at(raw),
            # REST 订单没有可靠的签收时间，只有 fulfillment 的 shipment_status；
            # 这里不猜，留给物流查询，避免把「运输中」说成「已签收」。
            "delivered_at": None,
            "items": [
                {
                    "product_id": split_sku(i.get("sku"))[0] or str(i.get("product_id") or ""),
                    "product_name": i.get("title"),
                    "size": i.get("variant_title") or split_sku(i.get("sku"))[1],
                    "qty": int(i.get("quantity") or 0),
                    "unit_price": _money(i.get("price")),
                }
                for i in raw.get("line_items") or []
            ],
        }
    )
    return order


def map_stock(raw: dict) -> dict:
    available = max(int(raw.get("inventory_quantity") or 0), 0)
    return {
        "sku": raw.get("sku"),
        "product_id": raw.get("product_id"),
        "size": raw.get("variant_title"),
        "color": raw.get("color"),
        "available": available,
        "reserved": 0,
        "warehouse": raw.get("warehouse") or "Shopify 仓",
        "low_stock": available <= 5,
    }


def map_product(raw: dict) -> dict:
    variants = raw.get("variants") or []
    price = variants[0].get("price") if variants else 0
    return {
        "product_id": split_sku(variants[0].get("sku") if variants else "")[0]
        or str(raw.get("id") or ""),
        "name": raw.get("title"),
        "price": _money(price),
        "currency": raw.get("currency") or "SGD",
        "category": raw.get("product_type") or "SHOES",
    }


def map_shop(raw: dict) -> dict:
    return {
        "shop_name": raw.get("name"),
        "region": raw.get("country_name"),
        "status": "active",
        "currency": raw.get("currency"),
    }
