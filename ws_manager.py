import asyncio
import json
import logging
import time
from typing import Callable, Awaitable

import websockets

from config import HL_WS_URL
import storage

logger = logging.getLogger(__name__)

SUBSCRIPTION_TYPES = [
    "userFills",
    "userFundings",
    "userNonFundingLedgerUpdates",
]


class WSManager:
    def __init__(
        self,
        on_event: Callable[[str, str, dict], Awaitable[None]],
        on_fill: Callable[[str, dict], Awaitable[None]] | None = None,
    ):
        self.on_event = on_event
        self.on_fill = on_fill
        self._ws = None
        self._running = False
        self._task: asyncio.Task | None = None
        self._subscribed_wallets: set[str] = set()
        self._subscription_times: dict[str, float] = {}

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self):
        self._running = False
        if self._ws:
            await self._ws.close()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    @property
    def connected(self) -> bool:
        return self._ws is not None and self._ws.open

    async def subscribe(self, wallet: str):
        wallet = wallet.lower()
        self._subscribed_wallets.add(wallet)
        self._subscription_times[wallet] = time.time()
        if self.connected:
            await self._send_subscriptions(wallet, subscribe=True)

    async def unsubscribe(self, wallet: str):
        wallet = wallet.lower()
        self._subscribed_wallets.discard(wallet)
        self._subscription_times.pop(wallet, None)
        if self.connected:
            await self._send_subscriptions(wallet, subscribe=False)

    async def _send_subscriptions(self, wallet: str, subscribe: bool):
        method = "subscribe" if subscribe else "unsubscribe"
        for sub_type in SUBSCRIPTION_TYPES:
            msg = {
                "method": method,
                "subscription": {"type": sub_type, "user": wallet},
            }
            try:
                await self._ws.send(json.dumps(msg))
            except Exception as e:
                logger.error(f"Failed to {method} {sub_type} for {wallet}: {e}")

    async def _resubscribe_all(self):
        wallets = set(storage.get_wallets().keys())
        self._subscribed_wallets = wallets
        sub_time = time.time()
        for wallet in wallets:
            self._subscription_times[wallet] = sub_time
            await self._send_subscriptions(wallet, subscribe=True)
        logger.info(f"Resubscribed to {len(wallets)} wallets")

    def _should_notify(self, wallet: str, event: dict) -> bool:
        sub_time = self._subscription_times.get(wallet)
        if sub_time is None:
            return False

        event_time_ms = event.get("time")
        if event_time_ms:
            event_time = event_time_ms / 1000
            return event_time > sub_time

        return time.time() - sub_time > 3

    async def _run_loop(self):
        backoff = 1
        while self._running:
            try:
                async with websockets.connect(HL_WS_URL) as ws:
                    self._ws = ws
                    backoff = 1
                    logger.info("WebSocket connected")
                    await self._resubscribe_all()
                    async for raw in ws:
                        await self._handle_message(raw)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                self._ws = None
                if self._running:
                    logger.info(f"Reconnecting in {backoff}s...")
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60)

    async def _handle_message(self, raw: str):
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        channel = msg.get("channel")
        data = msg.get("data")
        if not channel or not data:
            return

        subscription = msg.get("data", {})
        user = subscription.get("user", "").lower() if isinstance(subscription, dict) else ""

        if channel == "userFills":
            wallet = data.get("user", "").lower()
            for fill in data.get("fills", []):
                if not self._should_notify(wallet, fill):
                    continue
                if fill.get("liquidation"):
                    await self.on_event(wallet, "liquidations", fill)
                elif self.on_fill:
                    await self.on_fill(wallet, fill)
                else:
                    await self.on_event(wallet, "fills", fill)

        elif channel == "userFundings":
            wallet = data.get("user", "").lower()
            for funding in data.get("fundings", []):
                if not self._should_notify(wallet, funding):
                    continue
                await self.on_event(wallet, "funding", funding)

        elif channel == "userNonFundingLedgerUpdates":
            wallet = data.get("user", "").lower()
            for update in data.get("nonFundingLedgerUpdates", []):
                if not self._should_notify(wallet, update):
                    continue
                await self.on_event(wallet, "transfers", update)
