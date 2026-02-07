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


async def get_all_positions(wallet: str) -> list[dict]:
    data = await get_clearinghouse_state(wallet)
    if not data:
        return []

    positions = []
    for pos in data.get("assetPositions", []):
        position = pos.get("position", {})
        szi = position.get("szi", "0")

        if float(szi) == 0:
            continue

        positions.append({
            "coin": position.get("coin"),
            "szi": szi,
            "leverage": position.get("leverage", {}).get("value"),
            "liquidation_px": position.get("liquidationPx"),
            "entry_px": position.get("entryPx"),
            "unrealized_pnl": position.get("unrealizedPnl"),
            "return_on_equity": position.get("returnOnEquity"),
        })

    return positions
