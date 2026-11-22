"""渠道快照的简单落库：按租户 + 平台 + 实体 + 外部 ID 覆盖写。

不做订单/商品的正规化拆表，也不做增量同步；只保存最近一次成功结果，
让渠道故障时可以先回放缓存，再决定是否回落本地库。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import engine
from ..models import ChannelSnapshot
from ..tenancy import current_tenant


async def ensure_tables() -> None:
    """随启动建表，兼容已经初始化过的 MySQL；失败不阻断启动。"""
    async with engine.begin() as conn:
        await conn.run_sync(ChannelSnapshot.__table__.create, checkfirst=True)


async def save_snapshot(
    db: AsyncSession,
    *,
    platform: str,
    entity: str,
    external_id: str,
    payload: dict,
) -> None:
    tenant = current_tenant()
    row = await db.scalar(
        select(ChannelSnapshot).where(
            ChannelSnapshot.tenant_id == tenant,
            ChannelSnapshot.platform == platform,
            ChannelSnapshot.entity == entity,
            ChannelSnapshot.external_id == external_id,
        )
    )
    if row is None:
        db.add(
            ChannelSnapshot(
                tenant_id=tenant,
                platform=platform,
                entity=entity,
                external_id=external_id,
                payload=payload,
            )
        )
    else:
        row.payload = payload
        row.fetched_at = datetime.now()
    await db.commit()


async def save_products(db: AsyncSession, *, platform: str, items: list[dict]) -> int:
    """商品列表整批落库，只提交一次；返回写入条数。"""
    tenant = current_tenant()
    saved = 0
    for item in items:
        external_id = str(item.get("product_id") or "").strip()
        if not external_id:
            continue
        row = await db.scalar(
            select(ChannelSnapshot).where(
                ChannelSnapshot.tenant_id == tenant,
                ChannelSnapshot.platform == platform,
                ChannelSnapshot.entity == "product",
                ChannelSnapshot.external_id == external_id,
            )
        )
        if row is None:
            db.add(
                ChannelSnapshot(
                    tenant_id=tenant,
                    platform=platform,
                    entity="product",
                    external_id=external_id,
                    payload=item,
                )
            )
        else:
            row.payload = item
            row.fetched_at = datetime.now()
        saved += 1
    if saved:
        await db.commit()
    return saved


def _row_to_dict(row: ChannelSnapshot) -> dict:
    return {
        "external_id": row.external_id,
        "payload": row.payload,
        "fetched_at": row.fetched_at.strftime("%Y-%m-%d %H:%M:%S") if row.fetched_at else None,
    }


async def load_snapshot(
    db: AsyncSession,
    *,
    platform: str,
    entity: str,
    external_id: str,
) -> dict | None:
    row = await db.scalar(
        select(ChannelSnapshot).where(
            ChannelSnapshot.tenant_id == current_tenant(),
            ChannelSnapshot.platform == platform,
            ChannelSnapshot.entity == entity,
            ChannelSnapshot.external_id == external_id,
        )
    )
    return _row_to_dict(row) if row else None


async def list_snapshots(
    db: AsyncSession,
    *,
    platform: str,
    entity: str,
    limit: int = 50,
) -> list[dict]:
    rows = (
        await db.scalars(
            select(ChannelSnapshot)
            .where(
                ChannelSnapshot.tenant_id == current_tenant(),
                ChannelSnapshot.platform == platform,
                ChannelSnapshot.entity == entity,
            )
            .order_by(ChannelSnapshot.fetched_at.desc())
            .limit(max(1, min(limit, 200)))
        )
    ).all()
    return [_row_to_dict(row) for row in rows]
