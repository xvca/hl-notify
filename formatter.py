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


def format_aggregated_fills(fills: list[dict], wallet: str, position_info: dict | None = None) -> str:
    if not fills:
        return ""

    first = fills[0]
    coin = first.get("coin", "???")
    side = first.get("side", "").upper()
    direction = first.get("dir", "")

    total_sz = sum(float(f.get("sz", 0)) for f in fills)
    total_notional = sum(float(f.get("sz", 0)) * float(f.get("px", 0)) for f in fills)
    avg_px = total_notional / total_sz if total_sz > 0 else 0

    total_pnl = sum(float(f.get("closedPnl", 0)) for f in fills)

    emoji = "📈" if side == "BUY" else "📉" if side == "SELL" else "📊"

    lines = [
        f"{emoji} {side} {format_number(total_sz, 4)} {coin} @ ${format_number(avg_px)}",
    ]

    if direction:
        lines.append(f"   Direction: {direction}")

    if len(fills) > 1:
        lines.append(f"   Fills: {len(fills)}")

    if position_info:
        leverage = position_info.get("leverage")
        liq_px = position_info.get("liquidation_px")

        if leverage:
            lines.append(f"   Leverage: {leverage}x")

        if liq_px:
            try:
                liq_price = float(liq_px)
                if liq_price > 0:
                    lines.append(f"   Liquidation: ${format_number(liq_price)}")
            except (ValueError, TypeError):
                pass

    if total_pnl != 0:
        sign = "+" if total_pnl > 0 else ""
        lines.append(f"   PnL: {sign}${format_number(total_pnl)}")

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


def format_positions(positions: list[dict], wallet: str) -> str:
    if not positions:
        return f"No open positions for {short_addr(wallet)}"

    lines = [f"Positions for {short_addr(wallet)}:\n"]

    for pos in positions:
        coin = pos.get("coin", "???")
        szi = float(pos.get("szi", 0))
        side = "LONG" if szi > 0 else "SHORT"
        emoji = "📈" if szi > 0 else "📉"

        entry_px = pos.get("entry_px")
        leverage = pos.get("leverage")
        liq_px = pos.get("liquidation_px")
        pnl = pos.get("unrealized_pnl")
        roe = pos.get("return_on_equity")

        lines.append(f"{emoji} {side} {format_number(abs(szi), 4)} {coin}")

        if entry_px:
            lines.append(f"   Entry: ${format_number(float(entry_px))}")

        if leverage:
            lines.append(f"   Leverage: {leverage}x")

        if liq_px:
            try:
                liq_price = float(liq_px)
                if liq_price > 0:
                    lines.append(f"   Liquidation: ${format_number(liq_price)}")
            except (ValueError, TypeError):
                pass

        if pnl:
            pnl_val = float(pnl)
            sign = "+" if pnl_val > 0 else ""
            lines.append(f"   PnL: {sign}${format_number(pnl_val)}")

        if roe:
            roe_val = float(roe)
            sign = "+" if roe_val > 0 else ""
            lines.append(f"   ROE: {sign}{format_number(roe_val * 100)}%")

        lines.append("")

    return "\n".join(lines)
