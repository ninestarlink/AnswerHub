"""渠道网关：演示「前端 / Agent → 适配层 → Shopee / Shopify」的只读调用链。

三条读接口共用同一套降级策略：

- 优先走渠道（`mock` / `sandbox` / `live` 由 `CHANNEL_MODE` 决定）；
- `CHANNEL_MODE=local` 直接查本地库，标注 `source=local`；
- 渠道超时 / 鉴权失败 / 5xx 时回落本地 MySQL，标注 `source=local-fallback`；
- 响应里的 `source` 明确区分 `shopee-mock` / `shopify-live` / `local` / `local-fallback`，
  不把兜底数据伪装成平台结果。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..integrations.channels import (
    PLATFORMS,
    ChannelNotFound,
    ChannelUnavailable,
    channel_health,
    channel_overview,
    get_channel,
    normalize_sku,
)
from ..models import ProductVariant
from .tools import _get_order, _search_products

router = APIRouter(prefix="/api/channels", tags=["channels"])


def _check_platform(platform: str) -> str:
    key = (platform or "").strip().lower()
    if key not in PLATFORMS:
        raise HTTPException(status_code=404, detail=f"未知渠道 {platform!r}，可选 {' / '.join(PLATFORMS)}")
    return key


async def _local_order(db: AsyncSession, order_no: str) -> dict:
    return await _get_order(db, order_no)


async def _local_stock(db: AsyncSession, code: str) -> dict:
    variant = await db.scalar(select(ProductVariant).where(ProductVariant.sku == code))
    if variant is None:
        raise HTTPException(status_code=404, detail=f"本地库也未找到 SKU {code}")
    return {
        "sku": variant.sku,
        "product_id": variant.product_id,
        "size": variant.size,
        "color": variant.color,
        "available": variant.stock,
        "reserved": 0,
        "warehouse": "本地库",
        "low_stock": variant.stock <= 5,
    }


async def _local_products(db: AsyncSession) -> dict:
    data = await _search_products(db, limit=50)
    return {
        "entity": "products",
        "count": data["count"],
        "items": [
            {
                "product_id": p["product_id"],
                "name": p["name"],
                "price": p["price"],
                "currency": "CNY",
                "category": (p["tags"] or ["SHOES"])[0],
            }
            for p in data["products"]
        ],
    }


@router.get("")
async def api_channel_overview():
    """渠道列表与当前模式，供渠道页渲染模式徽章。"""
    return channel_overview()


@router.get("/{platform}/health")
async def api_channel_health(platform: str):
    return await channel_health(_check_platform(platform))


@router.get("/{platform}/orders/{order_no}")
async def api_channel_order(platform: str, order_no: str, db: AsyncSession = Depends(get_db)):
    key = _check_platform(platform)
    adapter = get_channel(key)
    if adapter is None:
        return {**await _local_order(db, order_no), "source": "local"}

    note = ""
    try:
        data = await adapter.get_order(order_no.strip())
        return {**data, "source": adapter.name}
    except ChannelNotFound:
        # 平台明确说没有，就不要用本地库「猜」一个回来
        raise HTTPException(status_code=404, detail=f"{key} 中未找到订单 {order_no}")
    except ChannelUnavailable as exc:
        note = str(exc)
    except Exception as exc:  # 适配器实现里的未知异常同样降级，避免对话 500
        note = f"{exc.__class__.__name__}: {exc}"

    try:
        data = await _local_order(db, order_no)
    except HTTPException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=f"渠道不可用（{note}），本地库也没有订单 {order_no}",
        ) from exc
    return {**data, "source": "local-fallback", "note": note}


@router.get("/{platform}/stock/{sku}")
async def api_channel_stock(platform: str, sku: str, db: AsyncSession = Depends(get_db)):
    """按 SKU 查可售库存，如 /api/channels/shopee/stock/SKU-P1004-42。"""
    key = _check_platform(platform)
    code = normalize_sku(sku)
    adapter = get_channel(key)

    if adapter is None:
        return {**await _local_stock(db, code), "source": "local"}

    note = ""
    try:
        data = await adapter.get_stock(code)
        return {**data, "source": adapter.name}
    except ChannelNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ChannelUnavailable as exc:
        note = str(exc)
    except Exception as exc:
        note = f"{exc.__class__.__name__}: {exc}"

    try:
        data = await _local_stock(db, code)
    except HTTPException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=f"渠道不可用（{note}），本地库也没有 SKU {code}",
        ) from exc
    return {**data, "source": "local-fallback", "note": note}


@router.get("/{platform}/products")
async def api_channel_products(platform: str, db: AsyncSession = Depends(get_db)):
    """拉商品主数据，演示渠道 → 本地的同步方向。"""
    key = _check_platform(platform)
    adapter = get_channel(key)

    if adapter is None:
        return {**await _local_products(db), "source": "local"}

    note = ""
    try:
        data = await adapter.pull_master_data("products")
        return {**data, "source": adapter.name}
    except ChannelNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ChannelUnavailable as exc:
        note = str(exc)
    except Exception as exc:
        note = f"{exc.__class__.__name__}: {exc}"

    return {**await _local_products(db), "source": "local-fallback", "note": note}
