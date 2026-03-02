from formatter import format_positions

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
                "return_on_equity": "0.2",
            }
        ],
        HLP_VAULT_ADDRESS,
        {"message": "Showing open positions. Some DEX queries failed: default."},
    )

    assert "builder:HIP3" in text
    assert "Some DEX queries failed" in text
    assert "Leverage: 5x" in text
