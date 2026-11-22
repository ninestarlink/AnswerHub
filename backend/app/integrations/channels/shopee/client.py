"""Shopee Open API v2 只读客户端。

鉴权公式（v2 公共参数签名）：

    base_string = partner_id + path + timestamp + access_token + shop_id
    sign        = HMAC-SHA256(partner_key, base_string).hexdigest()

`sign` 与 `partner_id / timestamp / access_token / shop_id` 一起放在 query 里。
注意 `path` 必须与真实请求路径完全一致（含 `/api/v2` 前缀），签名才对得上。

接口统一返回信封 `{"error","message","request_id","response"}`：
`error` 非空即失败，业务数据在 `response` 里。
"""

from __future__ import annotations

import hashlib
import hmac
import time

import httpx

from ..base import ChannelAuthError, ChannelNotFound, ChannelUnavailable

SANDBOX_BASE = "https://partner.test-stable.shopeemobile.com"
PRODUCTION_BASE = "https://partner.shopeemobile.com"

_PATH_ORDER = "/api/v2/order/get_order_detail"
_PATH_ITEM_LIST = "/api/v2/product/get_item_list"
_PATH_ITEM_BASE = "/api/v2/product/get_item_base_info"
_PATH_MODELS = "/api/v2/product/get_model_list"
_PATH_SHOP = "/api/v2/shop/get_shop_info"
_PATH_TOKEN = "/api/v2/auth/access_token/get"

# 这些错误码更可能是签名 / Token 问题，单独提示排查方向
_AUTH_ERRORS = {"error_auth", "error_param", "invalid_acceess_token", "invalid_access_token"}


def build_sign(partner_id: int | str, partner_key: str, path: str, timestamp: int, access_token: str, shop_id: int | str) -> str:
    """纯函数：便于单测用固定向量校验签名，不依赖网络。"""
    base = f"{partner_id}{path}{int(timestamp)}{access_token}{shop_id}"
    return hmac.new(
        (partner_key or "").encode("utf-8"),
        base.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


class ShopeeClient:
    """真实 / 沙箱 Shopee 客户端；mode 只用于展示来源。"""

    def __init__(
        self,
        *,
        partner_id: str,
        partner_key: str,
        shop_id: str,
        access_token: str,
        base_url: str = "",
        timeout: float = 8.0,
        mode: str = "sandbox",
    ) -> None:
        self.partner_id = (partner_id or "").strip()
        self.partner_key = (partner_key or "").strip()
        self.shop_id = (shop_id or "").strip()
        self.access_token = (access_token or "").strip()
        self.base_url = (base_url or "").strip().rstrip("/")
        self.timeout = timeout
        self.mode = mode

    # ------------------------------------------------------------------
    # 底层请求
    # ------------------------------------------------------------------
    def _signed_params(self, path: str, params: dict | None) -> dict:
        timestamp = int(time.time())
        query = {
            "partner_id": self.partner_id,
            "timestamp": timestamp,
            "access_token": self.access_token,
            "shop_id": self.shop_id,
            "sign": build_sign(
                self.partner_id,
                self.partner_key,
                path,
                timestamp,
                self.access_token,
                self.shop_id,
            ),
        }
        query.update(params or {})
        return query

    async def _request(self, path: str, params: dict | None = None) -> dict:
        if not self.base_url:
            raise ChannelUnavailable("SHOPEE_BASE_URL 未配置")
        if not (self.partner_id and self.partner_key and self.shop_id and self.access_token):
            raise ChannelUnavailable(
                "Shopee 凭证未配置（需要 SHOPEE_PARTNER_ID / PARTNER_KEY / SHOP_ID / ACCESS_TOKEN）"
            )

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                # 沙箱域名走公网，但演示机常有系统代理；这里显式不让环境代理接管，行为更可控
                trust_env=False,
            ) as client:
                resp = await client.get(path, params=self._signed_params(path, params))
        except httpx.TimeoutException as exc:
            raise ChannelUnavailable(f"Shopee 请求超时（>{self.timeout}s）") from exc
        except httpx.HTTPError as exc:
            raise ChannelUnavailable(f"Shopee 请求失败：{exc.__class__.__name__}") from exc

        if resp.status_code in (401, 403):
            raise ChannelAuthError(f"Shopee 鉴权失败（HTTP {resp.status_code}），检查签名与 Token")
        if resp.status_code >= 500:
            raise ChannelUnavailable(f"Shopee 返回 HTTP {resp.status_code}")
        if resp.status_code >= 400:
            raise ChannelUnavailable(f"Shopee 返回 HTTP {resp.status_code}")

        try:
            payload = resp.json()
        except ValueError as exc:
            raise ChannelUnavailable("Shopee 返回的不是合法 JSON") from exc

        error = str((payload or {}).get("error") or "").strip()
        if error:
            message = payload.get("message") or error
            if error in _AUTH_ERRORS:
                raise ChannelAuthError(f"Shopee 鉴权错误：{error} / {message}")
            if "not_found" in error or "not_exist" in error:
                raise ChannelNotFound(f"Shopee 未找到数据：{message}")
            raise ChannelUnavailable(f"Shopee 返回错误：{error} / {message}")

        return payload.get("response") or {}

    # ------------------------------------------------------------------
    # 只读能力：返回原生 `response` 内容，映射交给 map.py
    # ------------------------------------------------------------------
    async def get_order_raw(self, order_no: str) -> dict:
        response = await self._request(
            _PATH_ORDER,
            {
                "order_sn_list": (order_no or "").strip(),
                "response_optional_fields": "item_list,recipient_address,payment_method,total_amount",
            },
        )
        rows = response.get("order_list") or []
        if not rows:
            raise ChannelNotFound(f"Shopee 中不存在订单 {order_no}")
        return rows[0]

    async def list_items(self, offset: int = 0, page_size: int = 50) -> dict:
        response = await self._request(
            _PATH_ITEM_LIST,
            {"offset": offset, "page_size": page_size, "item_status": "NORMAL"},
        )
        return {
            "item": response.get("item") or [],
            "has_next_page": bool(response.get("has_next_page")),
            "next_offset": response.get("next_offset") or 0,
        }

    async def get_item_base_info(self, item_ids: list[int]) -> list[dict]:
        if not item_ids:
            return []
        response = await self._request(
            _PATH_ITEM_BASE,
            {"item_id_list": ",".join(str(i) for i in item_ids)},
        )
        return response.get("item_list") or []

    async def get_model_list(self, item_id: int) -> list[dict]:
        response = await self._request(_PATH_MODELS, {"item_id": item_id})
        return response.get("model") or []

    async def get_shop_info(self) -> dict:
        response = await self._request(_PATH_SHOP)
        return response or {}

    async def probe(self) -> dict:
        shop = await self.get_shop_info()
        return {
            "shop": shop.get("shop_name"),
            "region": shop.get("region"),
            "endpoint": self.base_url,
            "note": "已完成一次只读探测（GET /api/v2/shop/get_shop_info）",
        }

    # ------------------------------------------------------------------
    # Token 刷新（文档化能力，当前演示不自动调用）
    # ------------------------------------------------------------------
    async def refresh_access_token(self, refresh_token: str) -> dict:
        """用 refresh_token 换新的 access_token / refresh_token（4 小时有效期）。"""
        if not (self.partner_id and self.partner_key):
            raise ChannelUnavailable("Shopee partner 凭证未配置，无法刷新 Token")
        path = _PATH_TOKEN
        timestamp = int(time.time())
        body = {
            "partner_id": int(self.partner_id),
            "refresh_token": refresh_token,
            "shop_id": int(self.shop_id),
        }
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=self.timeout, trust_env=False
            ) as client:
                resp = await client.post(
                    path,
                    params={
                        "partner_id": self.partner_id,
                        "timestamp": timestamp,
                        "sign": build_sign(
                            self.partner_id, self.partner_key, path, timestamp, "", ""
                        ),
                    },
                    json=body,
                )
        except httpx.HTTPError as exc:
            raise ChannelUnavailable(f"Shopee Token 刷新失败：{exc.__class__.__name__}") from exc

        payload = resp.json() if resp.content else {}
        if payload.get("error"):
            raise ChannelAuthError(f"Shopee Token 刷新失败：{payload.get('error')}")
        return payload
