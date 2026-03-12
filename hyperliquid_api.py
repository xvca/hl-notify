import asyncio
import aiohttp
import logging

logger = logging.getLogger(__name__)

API_URL = "https://api.hyperliquid.xyz/info"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=5)
_session: aiohttp.ClientSession | None = None


async def init_http_session():
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=REQUEST_TIMEOUT)


async def close_http_session():
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
    _session = None


def http_session_ready() -> bool:
    return _session is not None and not _session.closed


async def _get_session() -> aiohttp.ClientSession:
    if not http_session_ready():
        await init_http_session()
    return _session


async def _post_info(payload: dict) -> dict | list | None:
    try:
        session = await _get_session()
        async with session.post(API_URL, json=payload) as resp:
            if resp.status != 200:
                logger.warning(
                    "Hyperliquid info payload %s returned HTTP %s",
                    payload.get("type"),
                    resp.status,
                )
                return None
            return await resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch Hyperliquid info payload {payload.get('type')}: {e}")
        return None


def _format_dex_name(dex: str) -> str:
    return dex or "default"


def _display_coin(coin: str | None, dex: str) -> str | None:
    if coin is None:
        return None
    if not dex or not isinstance(coin, str) or coin.startswith(f"{dex}:"):
        return coin
    return f"{dex}:{coin}"


def _build_position(position: dict, prices: dict[str, float], dex: str) -> dict | None:
    szi = position.get("szi", "0")
    try:
        if float(szi) == 0:
            return None
    except (ValueError, TypeError):
        return None

    coin = position.get("coin")
    display_coin = _display_coin(coin, dex)
    entry_px = position.get("entryPx")
    leverage = position.get("leverage", {}).get("value")

    margin_used = None
    if entry_px and leverage:
        try:
            notional = abs(float(szi)) * float(entry_px)
            margin_used = notional / float(leverage)
        except (ValueError, TypeError, ZeroDivisionError):
            pass

    current_px = prices.get(coin)
    if current_px is None and isinstance(display_coin, str):
        current_px = prices.get(display_coin)

    return {
        "coin": coin,
        "display_coin": display_coin,
        "dex": dex,
        "szi": szi,
        "leverage": leverage,
        "liquidation_px": position.get("liquidationPx"),
        "entry_px": entry_px,
        "current_px": current_px,
        "margin_used": margin_used,
        "unrealized_pnl": position.get("unrealizedPnl"),
        "return_on_equity": position.get("returnOnEquity"),
        "funding_since_open": position.get("cumFunding", {}).get("sinceOpen"),
    }


async def get_perp_dexs() -> list[str]:
    data = await _post_info({"type": "perpDexs"})
    if not isinstance(data, list) or not data:
        return [""]

    dexs: list[str] = []
    for dex in data:
        if dex is None:
            dexs.append("")
        elif isinstance(dex, str):
            dexs.append(dex)
        elif isinstance(dex, dict):
            name = dex.get("name")
            if isinstance(name, str):
                dexs.append(name)

    if "" not in dexs:
        dexs.insert(0, "")

    # Preserve order while removing duplicates.
    return list(dict.fromkeys(dexs)) or [""]


async def get_clearinghouse_state(wallet: str, dex: str = "") -> dict | None:
    payload = {
        "type": "clearinghouseState",
        "user": wallet,
    }
    if dex:
        payload["dex"] = dex

    data = await _post_info(payload)
    return data if isinstance(data, dict) else None


async def _collect_positions(wallet: str) -> dict:
    dexs = await get_perp_dexs()
    state_results = await asyncio.gather(
        *(get_clearinghouse_state(wallet, dex) for dex in dexs),
        return_exceptions=True,
    )
    price_results = await asyncio.gather(
        *(get_market_prices(dex) for dex in dexs),
        return_exceptions=True,
    )

    positions = []
    failed_dexs = []
    checked_dexs = []

    for dex, data, prices in zip(dexs, state_results, price_results):
        checked_dexs.append(_format_dex_name(dex))
        if not isinstance(data, dict):
            failed_dexs.append(_format_dex_name(dex))
            continue

        price_map = prices if isinstance(prices, dict) else {}
        for pos in data.get("assetPositions", []):
            built = _build_position(pos.get("position", {}), price_map, dex)
            if built:
                positions.append(built)

    report = {
        "positions": positions,
        "checked_dexs": checked_dexs,
        "failed_dexs": failed_dexs,
        "status": "ok",
        "message": "",
        "hint": "",
    }

    if positions:
        if failed_dexs:
            report["message"] = (
                f"Showing open positions. Some DEX queries failed: {', '.join(failed_dexs)}."
            )
        return report

    if len(failed_dexs) == len(checked_dexs):
        report["status"] = "error"
        report["message"] = "Failed to query Hyperliquid positions right now."
        return report

    if failed_dexs:
        report["status"] = "partial"
        report["message"] = (
            "No open positions found in successful DEX responses. "
            f"Some DEX queries failed: {', '.join(failed_dexs)}."
        )
    else:
        report["status"] = "empty"
        report["message"] = (
            f"Checked {len(checked_dexs)} perp DEXes and found no non-zero positions."
        )

    report["hint"] = (
        "If this is an agent/signer wallet, try the master or sub-account address instead."
    )
    return report


async def get_position_info(wallet: str, coin: str) -> dict | None:
    report = await _collect_positions(wallet)
    for position in report["positions"]:
        if coin in (position.get("coin"), position.get("display_coin")):
            return position
    return None


async def get_market_prices(dex: str = "") -> dict[str, float]:
    payload = {"type": "allMids"}
    if dex:
        payload["dex"] = dex

    data = await _post_info(payload)
    if not isinstance(data, dict):
        return {}

    try:
        return {k: float(v) for k, v in data.items()}
    except (ValueError, TypeError):
        return {}


async def get_positions_report(wallet: str) -> dict:
    return await _collect_positions(wallet)
