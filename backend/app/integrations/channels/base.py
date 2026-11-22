"""渠道适配层契约：把 Shopee / Shopify 的差异收在这一层。

上层（REST 网关 / Agent 工具）只认一套返回结构：

- 订单：与 `routers/tools._get_order` 对齐（order_no / status / items / 时间字段）
- 库存：与商品 variant 对齐（sku / available / warehouse / low_stock）
- 商品：与商品主数据对齐（product_id / name / price / currency / category）

平台原生结构（Shopee 的 `response.order_list`、Shopify 的 `line_items`）只出现在
各自的 `map_*` 里，换接口版本时只有一个排查点。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

# 演示固定用东八区，不依赖服务器本地时区（Windows 上常是 UTC+8，但容器可能是 UTC）
TZ_CN = timezone(timedelta(hours=8))

PLATFORM_LABELS = {"shopee": "Shopee", "shopify": "Shopify"}


class ChannelError(RuntimeError):
    """渠道调用失败的基类：上层据此决定降级还是报错。"""


class ChannelUnavailable(ChannelError):
    """网络失败、超时、5xx、未配置。可降级到本地库。"""


class ChannelAuthError(ChannelUnavailable):
    """签名 / Token 失效：属于不可用的一种，但单独成类便于提示排查方向。"""


class ChannelNotFound(ChannelError):
    """平台明确返回「不存在」。不降级，避免拿本地旧数据冒充渠道结果。"""


class ChannelAdapter(Protocol):
    """两个平台都要实现的最小只读能力集。"""

    platform: str
    mode: str
    name: str

    async def get_order(self, order_no: str) -> dict:
        """按订单号查订单。Shopify 订单号形如 #1001。"""

    async def get_stock(self, sku: str) -> dict:
        """按 SKU 查可售库存。"""

    async def pull_master_data(self, entity: str) -> dict:
        """拉商品主数据（当前只用到 products）。"""

    async def probe(self) -> dict:
        """连通性自检。"""


def normalize_sku(value: str) -> str:
    """variant_id（p1004-42）或半成品编码统一成 SKU-P1004-42。"""
    raw = (value or "").strip().upper()
    if not raw:
        return ""
    return raw if raw.startswith("SKU-") else f"SKU-{raw}"


def split_sku(sku: str) -> tuple[str, str]:
    """SKU-P1004-42 → (p1004, 42)；仅商品级 SKU-P1004 → (p1004, "")。"""
    parts = normalize_sku(sku).split("-")
    if len(parts) < 2:
        return "", ""
    return parts[1].lower(), "-".join(parts[2:])


# 内部统一状态：与 routers/tools.STATUS_TEXT 保持一致
STATUS_TEXT = {
    "pending_payment": "待支付",
    "paid": "已支付待发货",
    "shipped": "已发货运输中",
    "delivered": "已签收",
    "completed": "已完成",
    "refunding": "退款/退货处理中",
    "cancelled": "已取消",
}


def status_text(status: str) -> str:
    return STATUS_TEXT.get(status, status or "unknown")


def _money(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _to_cn(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(TZ_CN)


def _iso_dt(value: Any) -> str | None:
    """ISO 8601（含 Z / 偏移）→ 东八区 `YYYY-MM-DD HH:MM`。"""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return _to_cn(datetime.fromisoformat(text)).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        # 平台偶尔返回不带时区的秒级字符串，直接截断到分钟兜底
        return text.replace("T", " ")[:16]


def _unix_dt(value: Any) -> str | None:
    """Shopee 的秒级时间戳 → 东八区 `YYYY-MM-DD HH:MM`。"""
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return datetime.fromtimestamp(seconds, TZ_CN).strftime("%Y-%m-%d %H:%M")


def empty_order(order_no: str) -> dict:
    """统一订单骨架，两个平台都从这里补齐，避免字段缺失导致前端渲染报错。"""
    return {
        "order_no": order_no,
        "status": "unknown",
        "status_text": "未知",
        "total_amount": 0.0,
        "discount_amount": 0.0,
        "pay_method": None,
        "address": None,
        "created_at": None,
        "paid_at": None,
        "shipped_at": None,
        "delivered_at": None,
        "items": [],
        "shipment": None,
        "events": [],
    }
