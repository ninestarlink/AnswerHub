"""行级租户隔离：tenant_id 的解析、上下文注入与 ORM 自动过滤。

设计约定：
- 请求进入时由中间件解析 JWT 的 `tenant` claim，写入 ContextVar；
- 继承 `TenantScoped` 的模型自动获得 `tenant_id` 列；
- `do_orm_execute` 给所有 SELECT 追加租户条件，`before_flush` 给新对象补 tenant_id，
  业务代码不需要在每个查询里手写 `where tenant_id = ...`，避免漏一处就越权；
- 确需跨租户统计时，显式传 `execution_options(include_all_tenants=True)`。
"""

from __future__ import annotations

import re
from contextvars import ContextVar, Token
from typing import ClassVar

import jwt
from sqlalchemy import String, bindparam
from sqlalchemy.orm import Mapped, mapped_column

from .config import settings

_TENANT_RE = re.compile(r"^[a-z0-9_-]{1,32}$")
_tenant_ctx: ContextVar[str] = ContextVar("tenant_id", default="demo")
_EVENTS_INSTALLED = False


class TenantScoped:
    """租户数据混入：所有需要行级隔离的表继承它。"""

    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # 事件注册后，用于给每个已映射模型追加 with_loader_criteria
    _tenant_models: ClassVar[list[type]] = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        TenantScoped._tenant_models.append(cls)


def normalize_tenant(value: str | None) -> str:
    """租户标识只允许小写字母、数字、下划线和短横线，非法值回落默认租户。"""
    raw = (value or "").strip().lower()
    if not raw or not _TENANT_RE.fullmatch(raw):
        return (settings.default_tenant or "demo").strip().lower()
    return raw


def current_tenant() -> str:
    return _tenant_ctx.get()


def set_tenant(value: str | None) -> Token:
    return _tenant_ctx.set(normalize_tenant(value))


def reset_tenant(token: Token) -> None:
    _tenant_ctx.reset(token)


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def tenant_from_request(
    authorization: str | None,
    header_tenant: str | None,
) -> str:
    """Token 里的 tenant 优先；未登录时仅在 dev/test 下允许用 X-Tenant-Id 调试。"""
    token = _bearer_token(authorization)
    if token:
        try:
            claims = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        except jwt.PyJWTError:
            claims = {}
        claim = claims.get("tenant") or claims.get("tenant_id")
        if claim:
            return normalize_tenant(str(claim))

    if header_tenant and settings.app_env in {"dev", "test"}:
        return normalize_tenant(header_tenant)
    return normalize_tenant(settings.default_tenant)


def install_tenant_events() -> None:
    """注册全局 ORM 事件。重复调用安全（例如测试里多次建引擎）。"""
    global _EVENTS_INSTALLED
    if _EVENTS_INSTALLED:
        return

    from sqlalchemy import event
    from sqlalchemy.orm import Session, with_loader_criteria

    @event.listens_for(Session, "do_orm_execute")
    def _inject_tenant_filter(execute_state) -> None:  # noqa: ANN001
        if not execute_state.is_select:
            return
        if execute_state.execution_options.get("include_all_tenants"):
            return

        tenant = current_tenant()
        statement = execute_state.statement
        for model in TenantScoped._tenant_models:
            statement = statement.options(
                with_loader_criteria(
                    model,
                    bindparam("tenant_id", tenant) == model.tenant_id,
                    include_aliases=True,
                )
            )
        execute_state.statement = statement

    @event.listens_for(Session, "before_flush")
    def _stamp_tenant(session, flush_context, instances) -> None:  # noqa: ANN001
        tenant = current_tenant()
        for obj in session.new:
            if isinstance(obj, TenantScoped) and not getattr(obj, "tenant_id", None):
                obj.tenant_id = tenant

    _EVENTS_INSTALLED = True
