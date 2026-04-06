from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.pricing import PricingService


class _FakePricingService(PricingService):
    async def check_service_limit(self, db, org_id: str):  # type: ignore[override]
        if org_id == "full-org":
            return False, "Plan limit reached (10/10)"
        return True, None


@pytest.mark.asyncio
async def test_pricing_enforce_blocks_when_limit_reached() -> None:
    svc = _FakePricingService()
    with pytest.raises(HTTPException) as exc:
        await svc.ensure_service_limit(db=None, org_id="full-org")
    assert exc.value.status_code == 403
    assert "Plan limit reached" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_pricing_enforce_allows_when_under_limit() -> None:
    svc = _FakePricingService()
    await svc.ensure_service_limit(db=None, org_id="ok-org")
