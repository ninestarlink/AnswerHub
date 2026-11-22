"""行级租户隔离单测：上下文、JWT 解析、ORM 自动过滤与写入补齐。"""

from __future__ import annotations

import time
import unittest

import jwt
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base
from app.models import ChannelSnapshot
from app.tenancy import (
    install_tenant_events,
    normalize_tenant,
    reset_tenant,
    set_tenant,
    tenant_from_request,
)


class TenantContextTest(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_tenant(" ACME-CN "), "acme-cn")
        self.assertEqual(normalize_tenant("bad tenant!"), settings.default_tenant)
        self.assertEqual(normalize_tenant(""), settings.default_tenant)

    def test_token_claim_wins(self):
        token = jwt.encode(
            {
                "sub": "u1",
                "tenant": "tenant-a",
                "exp": int(time.time()) + 60,
            },
            settings.secret_key,
            algorithm="HS256",
        )
        self.assertEqual(tenant_from_request(f"Bearer {token}", "tenant-b"), "tenant-a")

    def test_header_in_dev(self):
        self.assertEqual(tenant_from_request(None, "tenant-b"), "tenant-b")

    def test_context_reset(self):
        before = "demo"
        token = set_tenant("tenant-a")
        try:
            from app.tenancy import current_tenant

            self.assertEqual(current_tenant(), "tenant-a")
        finally:
            reset_tenant(token)
        from app.tenancy import current_tenant

        self.assertEqual(current_tenant(), before)


class TenantOrmTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_tenant_events()
        cls.engine = create_engine("sqlite://")
        Base.metadata.create_all(cls.engine, tables=[ChannelSnapshot.__table__])

    def setUp(self):
        with Session(self.engine) as session:
            session.execute(delete(ChannelSnapshot))
            session.commit()

    def _add(self, tenant: str, external_id: str) -> None:
        token = set_tenant(tenant)
        try:
            with Session(self.engine) as session:
                session.add(
                    ChannelSnapshot(
                        platform="shopee",
                        entity="order",
                        external_id=external_id,
                        payload={"order_no": external_id},
                    )
                )
                session.commit()
        finally:
            reset_tenant(token)

    def _list(self, tenant: str, **options) -> list[ChannelSnapshot]:
        token = set_tenant(tenant)
        try:
            with Session(self.engine) as session:
                stmt = select(ChannelSnapshot).execution_options(**options)
                return list(session.execute(stmt).scalars().all())
        finally:
            reset_tenant(token)

    def test_insert_stamps_tenant(self):
        self._add("tenant-a", "A-1")
        rows = self._list("tenant-a")
        self.assertEqual([row.external_id for row in rows], ["A-1"])
        self.assertEqual(rows[0].tenant_id, "tenant-a")

    def test_select_cannot_cross_tenant(self):
        self._add("tenant-a", "A-1")
        self._add("tenant-b", "B-1")
        self.assertEqual([row.external_id for row in self._list("tenant-a")], ["A-1"])
        self.assertEqual([row.external_id for row in self._list("tenant-b")], ["B-1"])

    def test_admin_can_include_all(self):
        self._add("tenant-a", "A-1")
        self._add("tenant-b", "B-1")
        rows = self._list("tenant-a", include_all_tenants=True)
        self.assertEqual(sorted(row.external_id for row in rows), ["A-1", "B-1"])


if __name__ == "__main__":
    unittest.main()
