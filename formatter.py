def short_addr(address: str) -> str:
    return f"{address[:6]}...{address[-4:]}"


def format_number(n: float, decimals: int = 2) -> str:
    return f"{n:,.{decimals}f}"


def format_fill(fill: dict, wallet: str) -> str:
    coin = fill.get("coin", "???")
    side = fill.get("side", "").upper()
    emoji = "📈" if side == "BUY" else "📉" if side == "SELL" else "📊"
    sz = float(fill.get("sz", 0))
    px = float(fill.get("px", 0))
    direction = fill.get("dir", "")
    closed_pnl = fill.get("closedPnl")

    lines = [
        f"{emoji} {side} {format_number(sz, 4)} {coin} @ ${format_number(px)}",
    ]
    if direction:
        lines.append(f"   Direction: {direction}")
    if closed_pnl and float(closed_pnl) != 0:
        pnl = float(closed_pnl)
        sign = "+" if pnl > 0 else ""
        lines.append(f"   PnL: {sign}${format_number(pnl)}")
    lines.append(f"   Wallet: {short_addr(wallet)}")
    return "\n".join(lines)


def format_liquidation(liq: dict, wallet: str) -> str:
    coin = liq.get("coin", "???")
    sz = float(liq.get("sz", 0))
    lines = [
        f"🔴 LIQUIDATION",
        f"   Asset: {coin}",
        f"   Size: {format_number(sz, 4)}",
        f"   Wallet: {short_addr(wallet)}",
    ]
    return "\n".join(lines)


def format_funding(funding: dict, wallet: str) -> str:
    coin = funding.get("coin", "???")
    usdc = float(funding.get("usdc", 0))
    rate = funding.get("fundingRate", "?")
    sign = "+" if usdc > 0 else ""
    emoji = "💰" if usdc > 0 else "💸"
    lines = [
        f"{emoji} FUNDING {coin}",
        f"   Payment: {sign}${format_number(usdc)}",
        f"   Rate: {rate}",
        f"   Wallet: {short_addr(wallet)}",
    ]
    return "\n".join(lines)


def format_transfer(transfer: dict, wallet: str) -> str:
    usdc = float(transfer.get("usdc", 0))
    delta_type = transfer.get("type", "unknown")
    emoji = "⬇️" if usdc > 0 else "⬆️"
    lines = [
        f"{emoji} TRANSFER ({delta_type})",
        f"   Amount: ${format_number(abs(usdc))}",
        f"   Wallet: {short_addr(wallet)}",
    ]
    return "\n".join(lines)
