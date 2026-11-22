"""Shopify Admin API 只读客户端。

鉴权用自定义请求头 `X-Shopify-Access-Token`，不需要签名；接口版本固定在路径里
（`/admin/api/{version}`），默认 `2024-10`，避免平台升级把字段悄悄换掉。

两件必须处理的事：
1. 分页：列表接口用 `Link` 响应头给出 `rel="next"` 的完整 URL；
2. 限流：429 会带 `Retry-After`，按秒数等待后重试，而不是直接把故障抛给上游。

订单查询用 `name` 过滤（值为 `#1001`），比拉全量再本地匹配更接近真实用法。
"""

from __future__ import annotations

import asyncio

import httpx

from ..base import ChannelAuthError, ChannelNotFound, ChannelUnavailable

_MAX_RETRY = 2
_RETRY_AFTER_CAP = 5.0


class ShopifyClient:
    def __init__(
        self,
        *,
        shop_domain: str,
        access_token: str,
        api_version: str = "2024-10",
        timeout: float = 8.0,
        mode: str = "live",
    ) -> None:
        domain = (shop_domain or "").strip().rstrip("/")
        for prefix in ("https://", "http://"):
            if domain.startswith(prefix):
                domain = domain[len(prefix) :]
        self.shop_domain = domain
        self.access_token = (access_token or "").strip()
        self.api_version = (api_version or "2024-10").strip()
        self.timeout = timeout
        self.mode = mode

    @property
    def base_url(self) -> str:
        return f"https://{self.shop_domain}" if self.shop_domain else ""

    @property
    def admin_path(self) -> str:
        return f"/admin/api/{self.api_version}"

    @staticmethod
    def _next_link(link_header: str | None) -> str | None:
        if not link_header:
            return None
        for part in link_header.split(","):
            if 'rel="next"' in part:
                start = part.find("<")
                end = part.find(">")
                if start != -1 and end > start:
                    return part[start + 1 : end]
        return None

    async def _request(self, path: str, params: dict | None = None) -> tuple[dict, httpx.Headers]:
        if not self.shop_domain:
            raise ChannelUnavailable("SHOPIFY_SHOP_DOMAIN 未配置")
        if not self.access_token:
            raise ChannelUnavailable("SHOPIFY_ACCESS_TOKEN 未配置")

        headers = {
            "X-Shopify-Access-Token": self.access_token,
            "Accept": "application/json",
        }
        url = f"{self.base_url}{self.admin_path}{path}"

        last_error = ""
        for attempt in range(_MAX_RETRY + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                    resp = await client.get(url, params=params, headers=headers)
            except httpx.TimeoutException as exc:
                raise ChannelUnavailable(f"Shopify 请求超时（>{self.timeout}s）") from exc
            except httpx.HTTPError as exc:
                raise ChannelUnavailable(f"Shopify 请求失败：{exc.__class__.__name__}") from exc

            if resp.status_code == 429 and attempt < _MAX_RETRY:
                try:
                    wait = float(resp.headers.get("Retry-After") or 1)
                except ValueError:
                    wait = 1.0
                await asyncio.sleep(min(wait, _RETRY_AFTER_CAP))
                last_error = "429 限流"
                continue

            if resp.status_code == 404:
                raise ChannelNotFound(f"Shopify 返回 404：{path}")
            if resp.status_code in (401, 403):
                raise ChannelAuthError("Shopify 鉴权失败，检查 SHOPIFY_ACCESS_TOKEN 与 scope")
            if resp.status_code >= 400:
                detail = ""
                try:
                    detail = (resp.json() or {}).get("errors") or ""
                except ValueError:
                    detail = resp.text[:120]
                raise ChannelUnavailable(f"Shopify 返回 HTTP {resp.status_code}：{detail}")

            try:
                return resp.json() or {}, resp.headers
            except ValueError as exc:
                raise ChannelUnavailable("Shopify 返回的不是合法 JSON") from exc

        raise ChannelUnavailable(f"Shopify 请求失败：{last_error or '未知原因'}")

    async def get_order_raw(self, order_no: str) -> dict:
        key = (order_no or "").strip()
        if not key.startswith("#"):
            key = f"#{key}"
        payload, _ = await self._request(
            "/orders.json",
            {"status": "any", "name": key, "limit": 1},
        )
        rows = payload.get("orders") or []
        if not rows:
            raise ChannelNotFound(f"Shopify 中不存在订单 {order_no}")
        return rows[0]

    async def list_products(self, limit: int = 50) -> list[dict]:
        """最多翻 3 页（默认 50 条/页），够演示主数据同步，也避免异常店铺拖垮请求。"""
        rows: list[dict] = []
        params = {"limit": max(1, min(int(limit or 50), 250))}
        next_url: str | None = None

        for _ in range(3):
            if next_url:
                url, query = next_url, None
            else:
                url, query = f"{self.base_url}{self.admin_path}/products.json", params
            try:
                async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                    resp = await client.get(
                        url,
                        params=query,
                        headers={"X-Shopify-Access-Token": self.access_token, "Accept": "application/json"},
                    )
            except httpx.HTTPError as exc:
                raise ChannelUnavailable(f"Shopify 请求失败：{exc.__class__.__name__}") from exc
            if resp.status_code in (401, 403):
                raise ChannelAuthError("Shopify 鉴权失败，检查 SHOPIFY_ACCESS_TOKEN 与 scope")
            if resp.status_code >= 400:
                raise ChannelUnavailable(f"Shopify 返回 HTTP {resp.status_code}")

            payload = resp.json() or {}
            rows.extend(payload.get("products") or [])
            next_url = self._next_link(resp.headers.get("link"))
            if not next_url:
                break
        return rows

    async def get_shop_info(self) -> dict:
        payload, _ = await self._request("/shop.json")
        return payload.get("shop") or {}

    async def probe(self) -> dict:
        shop = await self.get_shop_info()
        return {
            "shop": shop.get("name"),
            "domain": shop.get("domain") or self.shop_domain,
            "api_version": self.api_version,
            "note": "已完成一次只读探测（GET /admin/api/{version}/shop.json）",
        }
