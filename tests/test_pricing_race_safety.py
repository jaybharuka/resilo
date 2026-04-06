from __future__ import annotations

import asyncio

import pytest


class _ConcurrentPricingGate:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.current = 0
        self._lock = asyncio.Lock()

    async def reserve(self) -> bool:
        async with self._lock:
            if self.current >= self.limit:
                return False
            self.current += 1
            return True


@pytest.mark.asyncio
async def test_concurrent_creations_never_exceed_limit() -> None:
    gate = _ConcurrentPricingGate(limit=3)

    async def create_one() -> bool:
        await asyncio.sleep(0)
        return await gate.reserve()

    results = await asyncio.gather(*(create_one() for _ in range(10)))

    assert sum(results) == 3
    assert gate.current == 3
