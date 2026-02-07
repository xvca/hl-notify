import aiohttp
import logging

logger = logging.getLogger(__name__)

API_URL = "https://api.hyperliquid.xyz/info"


async def get_clearinghouse_state(wallet: str) -> dict | None:
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "type": "clearinghouseState",
                "user": wallet,
            }
            async with session.post(API_URL, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch clearinghouse state: {e}")
        return None


async def get_position_info(wallet: str, coin: str) -> dict | None:
    data = await get_clearinghouse_state(wallet)
    if not data:
        return None

    positions = data.get("assetPositions", [])
    for pos in positions:
        position = pos.get("position", {})
        if position.get("coin") == coin:
            return {
                "coin": coin,
                "szi": position.get("szi"),
                "leverage": position.get("leverage", {}).get("value"),
                "liquidation_px": position.get("liquidationPx"),
                "entry_px": position.get("entryPx"),
                "unrealized_pnl": position.get("unrealizedPnl"),
            }
    return None


async def get_market_prices() -> dict[str, float]:
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"type": "allMids"}
            async with session.post(API_URL, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json()
                return {k: float(v) for k, v in data.items()}
    except Exception as e:
        logger.error(f"Failed to fetch market prices: {e}")
        return {}


async def get_all_positions(wallet: str) -> list[dict]:
    data = await get_clearinghouse_state(wallet)
    if not data:
        return []

    prices = await get_market_prices()

    positions = []
    for pos in data.get("assetPositions", []):
        position = pos.get("position", {})
        szi = position.get("szi", "0")

        if float(szi) == 0:
            continue

        coin = position.get("coin")
        entry_px = position.get("entryPx")
        leverage_dict = position.get("leverage", {})
        leverage = leverage_dict.get("value")

        margin_used = None
        if entry_px and leverage:
            try:
                notional = abs(float(szi)) * float(entry_px)
                margin_used = notional / float(leverage)
            except (ValueError, TypeError, ZeroDivisionError):
                pass

        positions.append({
            "coin": coin,
            "szi": szi,
            "leverage": leverage,
            "liquidation_px": position.get("liquidationPx"),
            "entry_px": entry_px,
            "current_px": prices.get(coin),
            "margin_used": margin_used,
            "unrealized_pnl": position.get("unrealizedPnl"),
            "return_on_equity": position.get("returnOnEquity"),
        })

    return positions
