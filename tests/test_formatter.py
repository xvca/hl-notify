from formatter import format_funding, format_positions

# Public example wallet for test fixtures only; these tests use mocked data and
# do not depend on the address having live positions.
HLP_VAULT_ADDRESS = "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303"


def test_format_positions_shows_diagnostics_for_empty_results():
    text = format_positions(
        [],
        HLP_VAULT_ADDRESS,
        {
            "message": "Checked 3 perp DEXes and found no non-zero positions.",
            "hint": "If this is an agent/signer wallet, try the master or sub-account address instead.",
        },
    )

    assert "No open positions" in text
    assert "Checked 3 perp DEXes" in text
    assert "agent/signer" in text


def test_format_positions_shows_report_message_and_display_coin():
    text = format_positions(
        [
            {
                "display_coin": "builder:HIP3",
                "szi": "2",
                "entry_px": "12.5",
                "current_px": 13.0,
                "leverage": {"type": "cross", "value": 5}.get("value"),
                "margin_used": 5.0,
                "unrealized_pnl": "1.0",
                "funding_since_open": "-0.75",
                "return_on_equity": "0.2",
            }
        ],
        HLP_VAULT_ADDRESS,
        {"message": "Showing open positions. Some DEX queries failed: default."},
    )

    assert "builder:HIP3" in text
    assert "Some DEX queries failed" in text
    assert "<b>Leverage:</b> 5x" in text
    assert "<b>Funding (open):</b> +$0.75" in text
    assert "<b>Net PnL:</b> +$1.75" in text


def test_format_funding_uses_annualized_rate():
    text = format_funding(
        {
            "coin": "cash:USA500",
            "usdc": "-0.57",
            "fundingRate": "-0.0000208125",
        },
        HLP_VAULT_ADDRESS,
    )

    assert "<b>Funding cash:USA500</b>" in text
    assert "<b>Payment:</b> $-0.57" in text
    assert "<b>Rate (annualized):</b> -18.23%" in text
