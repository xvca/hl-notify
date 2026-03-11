from html import escape


def short_addr(address: str) -> str:
    return f"{address[:6]}...{address[-4:]}"


def format_number(n: float, decimals: int = 2) -> str:
    return f"{n:,.{decimals}f}"


def format_signed_usd(value: float, decimals: int = 2) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}${format_number(value, decimals)}"


def format_percent(value: float, decimals: int = 2) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{format_number(value, decimals)}%"


def annualize_funding_rate(rate: float) -> float:
    return rate * 24 * 365 * 100


def render_message_html(title: str, rows: list[tuple[str, str]], accent: str | None = None) -> str:
    safe_title = escape(title)
    if accent:
        safe_title = f"{escape(accent)} {safe_title}"

    lines = [f"<b>{safe_title}</b>"]
    for label, value in rows:
        lines.append(f"<b>{escape(label)}:</b> {escape(value)}")
    return "\n".join(lines)


def format_fill(fill: dict, wallet: str) -> str:
    coin = fill.get("coin", "???")
    side = fill.get("side", "").upper()
    sz = float(fill.get("sz", 0))
    px = float(fill.get("px", 0))
    direction = fill.get("dir", "")
    closed_pnl = fill.get("closedPnl")
    rows = [("Price", f"{format_number(sz, 4)} {coin} @ ${format_number(px)}")]
    if direction:
        rows.append(("Direction", direction))
    if closed_pnl and float(closed_pnl) != 0:
        pnl = float(closed_pnl)
        rows.append(("PnL", format_signed_usd(pnl)))
    rows.append(("Wallet", short_addr(wallet)))
    return render_message_html(f"{side} {coin}", rows, accent="Trade")


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

    rows = [("Average", f"{format_number(total_sz, 4)} {coin} @ ${format_number(avg_px)}")]

    if direction:
        rows.append(("Direction", direction))

    if len(fills) > 1:
        rows.append(("Fills", str(len(fills))))

    if position_info:
        leverage = position_info.get("leverage")
        liq_px = position_info.get("liquidation_px")

        if leverage:
            rows.append(("Leverage", f"{leverage}x"))

        if liq_px:
            try:
                liq_price = float(liq_px)
                if liq_price > 0:
                    rows.append(("Liquidation", f"${format_number(liq_price)}"))
            except (ValueError, TypeError):
                pass

    if total_pnl != 0:
        rows.append(("PnL", format_signed_usd(total_pnl)))

    rows.append(("Wallet", short_addr(wallet)))
    return render_message_html(f"{side} {coin}", rows, accent="Trades")


def format_liquidation(liq: dict, wallet: str) -> str:
    coin = liq.get("coin", "???")
    sz = float(liq.get("sz", 0))
    return render_message_html(
        f"Liquidation {coin}",
        [
            ("Size", format_number(sz, 4)),
            ("Wallet", short_addr(wallet)),
        ],
    )


def format_funding(funding: dict, wallet: str) -> str:
    coin = funding.get("coin", "???")
    usdc = float(funding.get("usdc", 0))
    annualized = None
    try:
        annualized = annualize_funding_rate(float(funding.get("fundingRate", 0)))
    except (ValueError, TypeError):
        pass

    rows = [
        ("Payment", format_signed_usd(usdc)),
    ]
    if annualized is not None:
        rows.append(("Rate (annualized)", format_percent(annualized, 2)))
    rows.append(("Wallet", short_addr(wallet)))
    return render_message_html(f"Funding {coin}", rows)


def format_transfer(transfer: dict, wallet: str) -> str:
    usdc = float(transfer.get("usdc", 0))
    delta_type = transfer.get("type", "unknown")
    return render_message_html(
        f"Transfer {delta_type}",
        [
            ("Amount", f"${format_number(abs(usdc))}"),
            ("Wallet", short_addr(wallet)),
        ],
    )


def format_positions(positions: list[dict], wallet: str, report: dict | None = None) -> str:
    if not positions:
        lines = [f"<b>Positions {escape(short_addr(wallet))}</b>", "No open positions."]
        if report:
            message = report.get("message")
            hint = report.get("hint")
            if message:
                lines.append(escape(message))
            if hint:
                lines.append(escape(hint))
        return "\n".join(lines)

    lines = [f"<b>Positions {escape(short_addr(wallet))}</b>"]
    if report and report.get("message"):
        lines.append(escape(report["message"]))

    for pos in positions:
        coin = pos.get("display_coin") or pos.get("coin", "???")
        szi = float(pos.get("szi", 0))
        side = "LONG" if szi > 0 else "SHORT"

        entry_px = pos.get("entry_px")
        current_px = pos.get("current_px")
        leverage = pos.get("leverage")
        liq_px = pos.get("liquidation_px")
        margin_used = pos.get("margin_used")
        pnl = pos.get("unrealized_pnl")
        roe = pos.get("return_on_equity")
        funding_since_open = pos.get("funding_since_open")
        funding_display = None
        net_pnl = None

        if funding_since_open not in (None, "", "0", "0.0"):
            funding_display = float(funding_since_open) * -1

        if pnl not in (None, "", "0", "0.0"):
            pnl_val = float(pnl)
            if funding_display is not None:
                net_pnl = pnl_val + funding_display
        else:
            pnl_val = None

        rows = [("Position", f"{side} {format_number(abs(szi), 4)} {coin}")]

        if entry_px:
            rows.append(("Entry", f"${format_number(float(entry_px))}"))

        if current_px:
            rows.append(("Current", f"${format_number(current_px)}"))

        if leverage:
            rows.append(("Leverage", f"{leverage}x"))

        if margin_used:
            rows.append(("Margin", f"${format_number(margin_used)}"))

        if liq_px:
            try:
                liq_price = float(liq_px)
                if liq_price > 0:
                    rows.append(("Liquidation", f"${format_number(liq_price)}"))
            except (ValueError, TypeError):
                pass

        if pnl_val is not None:
            rows.append(("PnL", format_signed_usd(pnl_val)))

        if funding_display is not None:
            rows.append(("Funding (open)", format_signed_usd(funding_display)))

        if net_pnl is not None:
            rows.append(("Net PnL", format_signed_usd(net_pnl)))

        if roe:
            roe_val = float(roe)
            rows.append(("ROE", format_percent(roe_val * 100)))

        lines.append("")
        lines.append(render_message_html(coin, rows))

    return "\n".join(lines)
