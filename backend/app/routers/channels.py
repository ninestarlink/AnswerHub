"""渠道网关：演示「前端 / Agent → 适配层 → Shopee / Shopify」的只读调用链。

读取顺序：
1. 渠道实时查询（`mock` / `sandbox` / `live` 由 `CHANNEL_MODE` 决定）；
2. 成功后把最近一次结果按租户写入 `channel_snapshots`；
3. 渠道超时 / 鉴权失败 / 5xx 时先回放该租户的最近快照（`source=channel-cache`）；
4. 没有快照再回落本地 MySQL（`source=local-fallback`）。

响应里的 `source` 明确区分 `shopee-mock` / `shopify-live` / `channel-cache` /
`local` / `local-fallback`，不把兜底数据伪装成平台结果。
"""

from __future__ import annotations

import logging

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
from ..services import channel_store
from ..tenancy import current_tenant
from .tools import _get_order, _search_products

logger = logging.getLogger("channels")
router = APIRouter(prefix="/api/channels", tags=["channels"])

_SNAPSHOT_ENTITIES = {"order", "stock", "product"}


def _check_platform(platform: str) -> str:
    key = (platform or "").strip().lower()
    if key not in PLATFORMS:
        raise HTTPException(status_code=404, detail=f"未知渠道 {platform!r}，可选 {' / '.join(PLATFORMS)}")
    return key


def _check_entity(entity: str) -> str:
    key = (entity or "").strip().lower()
    if key not in _SNAPSHOT_ENTITIES:
        raise HTTPException(
            status_code=404,
            detail=f"未知实体 {entity!r}，可选 {' / '.join(sorted(_SNAPSHOT_ENTITIES))}",
        )
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


async def _persist(
    db: AsyncSession,
    *,
    platform: str,
    entity: str,
    external_id: str,
    payload: dict,
) -> bool:
    """写穿快照；失败只记日志，不影响本次查询结果。"""
    try:
        await channel_store.save_snapshot(
            db,
            platform=platform,
            entity=entity,
            external_id=external_id,
            payload=payload,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.warning("渠道快照写入失败（%s/%s/%s）：%s", platform, entity, external_id, exc)
        return False


async def _persist_products(db: AsyncSession, platform: str, items: list[dict]) -> int:
    try:
        return await channel_store.save_products(db, platform=platform, items=items)
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.warning("渠道商品快照写入失败（%s）：%s", platform, exc)
        return 0


async def _cached(
    db: AsyncSession,
    *,
    platform: str,
    entity: str,
    external_id: str,
) -> dict | None:
    try:
        return await channel_store.load_snapshot(
            db, platform=platform, entity=entity, external_id=external_id
        )
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.warning("渠道快照读取失败（%s/%s/%s）：%s", platform, entity, external_id, exc)
        return None


async def _cached_list(
    db: AsyncSession,
    *,
    platform: str,
    entity: str,
    limit: int = 50,
) -> list[dict]:
    try:
        return await channel_store.list_snapshots(
            db, platform=platform, entity=entity, limit=limit
        )
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.warning("渠道快照列表读取失败（%s/%s）：%s", platform, entity, exc)
        return []


@router.get("")
async def api_channel_overview():
    """渠道列表与当前模式，供渠道页渲染模式徽章。"""
    return {**channel_overview(), "tenant_id": current_tenant()}


@router.get("/{platform}/health")
async def api_channel_health(platform: str):
    return {**await channel_health(_check_platform(platform)), "tenant_id": current_tenant()}


@router.get("/{platform}/orders/{order_no}")
async def api_channel_order(platform: str, order_no: str, db: AsyncSession = Depends(get_db)):
    key = _check_platform(platform)
    adapter = get_channel(key)
    tenant = current_tenant()
    if adapter is None:
        return {**await _local_order(db, order_no), "source": "local", "tenant_id": tenant}

    note = ""
    try:
        data = await adapter.get_order(order_no.strip())
        stored = await _persist(
            db, platform=key, entity="order", external_id=order_no.strip(), payload=data
        )
        return {**data, "source": adapter.name, "tenant_id": tenant, "stored": stored}
    except ChannelNotFound:
        # 平台明确说没有，就不要用缓存或本地库「猜」一个回来
        raise HTTPException(status_code=404, detail=f"{key} 中未找到订单 {order_no}")
    except ChannelUnavailable as exc:
        note = str(exc)
    except Exception as exc:  # 适配器实现里的未知异常同样降级，避免对话 500
        note = f"{exc.__class__.__name__}: {exc}"

    cached = await _cached(db, platform=key, entity="order", external_id=order_no.strip())
    if cached:
        return {
            **cached["payload"],
            "source": "channel-cache",
            "tenant_id": tenant,
            "cached_at": cached["fetched_at"],
            "note": note,
        }

    try:
        data = await _local_order(db, order_no)
    except HTTPException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=f"渠道不可用（{note}），本地库也没有订单 {order_no}",
        ) from exc
    return {**data, "source": "local-fallback", "tenant_id": tenant, "note": note}


@router.get("/{platform}/stock/{sku}")
async def api_channel_stock(platform: str, sku: str, db: AsyncSession = Depends(get_db)):
    """按 SKU 查可售库存，如 /api/channels/shopee/stock/SKU-P1004-42。"""
    key = _check_platform(platform)
    code = normalize_sku(sku)
    adapter = get_channel(key)
    tenant = current_tenant()

    if adapter is None:
        return {**await _local_stock(db, code), "source": "local", "tenant_id": tenant}

    note = ""
    try:
        data = await adapter.get_stock(code)
        stored = await _persist(
            db, platform=key, entity="stock", external_id=code, payload=data
        )
        return {**data, "source": adapter.name, "tenant_id": tenant, "stored": stored}
    except ChannelNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ChannelUnavailable as exc:
        note = str(exc)
    except Exception as exc:
        note = f"{exc.__class__.__name__}: {exc}"

    cached = await _cached(db, platform=key, entity="stock", external_id=code)
    if cached:
        return {
            **cached["payload"],
            "source": "channel-cache",
            "tenant_id": tenant,
            "cached_at": cached["fetched_at"],
            "note": note,
        }

    try:
        data = await _local_stock(db, code)
    except HTTPException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=f"渠道不可用（{note}），本地库也没有 SKU {code}",
        ) from exc
    return {**data, "source": "local-fallback", "tenant_id": tenant, "note": note}


@router.get("/{platform}/products")
async def api_channel_products(platform: str, db: AsyncSession = Depends(get_db)):
    """拉商品主数据，并把最近一次成功结果按租户落库。"""
    key = _check_platform(platform)
    adapter = get_channel(key)
    tenant = current_tenant()

    if adapter is None:
        return {**await _local_products(db), "source": "local", "tenant_id": tenant}

    note = ""
    try:
        data = await adapter.pull_master_data("products")
        stored = await _persist_products(db, key, data.get("items") or [])
        return {**data, "source": adapter.name, "tenant_id": tenant, "stored": stored}
    except ChannelNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ChannelUnavailable as exc:
        note = str(exc)
    except Exception as exc:
        note = f"{exc.__class__.__name__}: {exc}"

    cached = await _cached_list(db, platform=key, entity="product", limit=50)
    if cached:
        items = [row["payload"] for row in cached]
        return {
            "entity": "products",
            "count": len(items),
            "items": items,
            "source": "channel-cache",
            "tenant_id": tenant,
            "cached_at": cached[0]["fetched_at"],
            "note": note,
        }

    return {
        **await _local_products(db),
        "source": "local-fallback",
        "tenant_id": tenant,
        "note": note,
    }


@router.get("/{platform}/snapshots/{entity}")
async def api_channel_snapshots(
    platform: str,
    entity: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """查看当前租户已落库的渠道快照，用于验证行级隔离与降级回放。"""
    key = _check_platform(platform)
    kind = _check_entity(entity)
    rows = await channel_store.list_snapshots(
        db, platform=key, entity=kind, limit=limit
    )
    return {
        "tenant_id": current_tenant(),
        "platform": key,
        "entity": kind,
        "count": len(rows),
        "items": rows,
        "source": "channel-store",
    }


@router.get("/{platform}/snapshots/{entity}/{external_id}")
async def api_channel_snapshot(
    platform: str,
    entity: str,
    external_id: str,
    db: AsyncSession = Depends(get_db),
):
    key = _check_platform(platform)
    kind = _check_entity(entity)
    row = await channel_store.load_snapshot(
        db, platform=key, entity=kind, external_id=external_id
    )
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"租户 {current_tenant()} 下没有 {key}/{kind}/{external_id} 的快照",
        )
    return {
        **row,
        "tenant_id": current_tenant(),
        "platform": key,
        "entity": kind,
        "source": "channel-store",
    }
