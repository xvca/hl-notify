import aiohttp
import logging

logger = logging.getLogger(__name__)

API_URL = "https://api.hyperliquid.xyz/info"


async def get_position_info(wallet: str, coin: str) -> dict | None:
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "type": "clearinghouseState",
                "user": wallet,
            }
            async with session.post(API_URL, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()

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
    except Exception as e:
        logger.error(f"Failed to fetch position info: {e}")
        return None
