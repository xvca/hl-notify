import asyncio
import logging
from collections import defaultdict
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)


class FillAggregator:
    def __init__(self, on_batch: Callable[[str, list], Awaitable[None]], window_sec: float = 2.0):
        self.on_batch = on_batch
        self.window_sec = window_sec
        self._pending: dict[tuple[str, str, str], list] = defaultdict(list)
        self._timers: dict[tuple[str, str, str], asyncio.Task] = {}

    async def add_fill(self, wallet: str, fill: dict):
        coin = fill.get("coin", "")
        side = fill.get("side", "")
        direction = fill.get("dir", "")

        key = (wallet, coin, direction)
        self._pending[key].append(fill)

        if key in self._timers:
            self._timers[key].cancel()

        self._timers[key] = asyncio.create_task(self._flush_after_delay(key))

    async def _flush_after_delay(self, key: tuple[str, str, str]):
        await asyncio.sleep(self.window_sec)
        await self._flush(key)

    async def _flush(self, key: tuple[str, str, str]):
        fills = self._pending.pop(key, [])
        self._timers.pop(key, None)

        if not fills:
            return

        wallet = key[0]
        try:
            await self.on_batch(wallet, fills)
        except Exception as e:
            logger.error(f"Error processing batch: {e}")
