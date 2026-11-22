"""渠道工厂：把 `CHANNEL_MODE` + 平台覆盖映射到具体实现，进程内复用实例。

模式：
- `local`   ：不接平台，订单 / 库存 / 商品直接查本地 MySQL
- `mock`    ：内置虚构数据（默认，开箱即用，无账号无网络）
- `sandbox` ：Shopee 沙箱（带真实 v2 签名）；Shopify 没有沙箱环境，按 `live` 处理
- `live`    ：平台生产环境（需要真实 Token）

单平台可用 `SHOPEE_MODE` / `SHOPIFY_MODE` 覆盖全局 `CHANNEL_MODE`。
"""

from __future__ import annotations

import time

from ...config import settings
from .base import ChannelAdapter, ChannelError
from .shopee.adapter import ShopeeAdapter
from .shopee.client import PRODUCTION_BASE, SANDBOX_BASE, ShopeeClient
from .shopee.mock import MockShopeeClient
from .shopify.adapter import ShopifyAdapter
from .shopify.client import ShopifyClient
from .shopify.mock import MockShopifyClient

PLATFORMS = ("shopee", "shopify")

_cache: dict[tuple[str, str], ChannelAdapter] = {}
_VALID_MODES = {"local", "mock", "sandbox", "live"}


def channel_mode(platform: str) -> str:
    override = ""
    if platform == "shopee":
        override = settings.shopee_mode
    elif platform == "shopify":
        override = settings.shopify_mode
    mode = (override or settings.channel_mode or "mock").strip().lower()
    return mode if mode in _VALID_MODES else "mock"


def _build(platform: str, mode: str) -> ChannelAdapter:
    timeout = settings.channel_timeout

    if platform == "shopee":
        if mode == "mock":
            return ShopeeAdapter(MockShopeeClient(), mode="mock")
        base_url = settings.shopee_base_url or (SANDBOX_BASE if mode == "sandbox" else PRODUCTION_BASE)
        return ShopeeAdapter(
            ShopeeClient(
                partner_id=settings.shopee_partner_id,
                partner_key=settings.shopee_partner_key,
                shop_id=settings.shopee_shop_id,
                access_token=settings.shopee_access_token,
                base_url=base_url,
                timeout=timeout,
                mode=mode,
            ),
            mode=mode,
        )

    if platform == "shopify":
        if mode in ("mock", "sandbox"):
            return ShopifyAdapter(MockShopifyClient(), mode="mock")
        return ShopifyAdapter(
            ShopifyClient(
                shop_domain=settings.shopify_shop_domain,
                access_token=settings.shopify_access_token,
                api_version=settings.shopify_api_version,
                timeout=timeout,
                mode="live",
            ),
            mode="live",
        )

    raise ValueError(f"未知渠道 {platform!r}，可选 {' / '.join(PLATFORMS)}")


def get_channel(platform: str) -> ChannelAdapter | None:
    """返回当前模式的适配器；`local` 模式返回 None，由调用方直接走本地库。"""
    key = (platform or "").strip().lower()
    if key not in PLATFORMS:
        raise ValueError(f"未知渠道 {platform!r}，可选 {' / '.join(PLATFORMS)}")

    mode = channel_mode(key)
    if mode == "local":
        return None

    cached = _cache.get((key, mode))
    if cached is None:
        cached = _build(key, mode)
        _cache[(key, mode)] = cached
    return cached


async def channel_health(platform: str) -> dict:
    """连通性自检：失败不抛异常，只回报状态，供 /api/channels/{platform}/health。"""
    key = (platform or "").strip().lower()
    mode = channel_mode(key)
    if key not in PLATFORMS:
        raise ValueError(f"未知渠道 {platform!r}，可选 {' / '.join(PLATFORMS)}")

    adapter = get_channel(key)
    if adapter is None:
        return {
            "platform": key,
            "mode": "local",
            "ok": True,
            "adapter": None,
            "note": "未启用渠道，订单与库存直接查本地 MySQL",
        }

    started = time.perf_counter()
    try:
        probe = await adapter.probe()
        elapsed = int((time.perf_counter() - started) * 1000)
        return {
            "platform": key,
            "mode": mode,
            "ok": True,
            "adapter": adapter.name,
            "latency_ms": elapsed,
            "probe": probe,
        }
    except ChannelError as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        return {
            "platform": key,
            "mode": mode,
            "ok": False,
            "adapter": adapter.name,
            "latency_ms": elapsed,
            "error": str(exc),
            "note": "调用失败时上层会自动降级到本地库，并在响应的 source 字段标注",
        }


def channel_overview() -> dict:
    """概览：给前端首页 / 渠道页做模式徽章，不发网络请求。"""
    return {
        "default_mode": (settings.channel_mode or "mock").strip().lower(),
        "platforms": [
            {
                "platform": key,
                "label": "Shopee" if key == "shopee" else "Shopify",
                "mode": channel_mode(key),
            }
            for key in PLATFORMS
        ],
    }
