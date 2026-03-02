import asyncio

import hyperliquid_api


def test_get_perp_dexs_extracts_names_and_deduplicates(monkeypatch):
    async def fake_post_info(payload):
        assert payload == {"type": "perpDexs"}
        return [None, {"name": "builder-a"}, "legacy", {"name": "builder-a"}, {"foo": "bar"}]

    monkeypatch.setattr(hyperliquid_api, "_post_info", fake_post_info)

    result = asyncio.run(hyperliquid_api.get_perp_dexs())

    assert result == ["", "builder-a", "legacy"]


def test_get_positions_report_marks_partial_failures(monkeypatch):
    async def fake_get_perp_dexs():
        return ["", "builder-a"]

    async def fake_get_clearinghouse_state(wallet, dex=""):
        if dex == "":
            return {"assetPositions": []}
        return None

    async def fake_get_market_prices(dex=""):
        return {}

    monkeypatch.setattr(hyperliquid_api, "get_perp_dexs", fake_get_perp_dexs)
    monkeypatch.setattr(hyperliquid_api, "get_clearinghouse_state", fake_get_clearinghouse_state)
    monkeypatch.setattr(hyperliquid_api, "get_market_prices", fake_get_market_prices)

    report = asyncio.run(hyperliquid_api.get_positions_report("0xabc"))

    assert report["positions"] == []
    assert report["status"] == "partial"
    assert report["failed_dexs"] == ["builder-a"]
    assert "agent/signer" in report["hint"]


def test_get_positions_report_formats_hip3_positions(monkeypatch):
    async def fake_get_perp_dexs():
        return ["", "builder-a"]

    async def fake_get_clearinghouse_state(wallet, dex=""):
        if dex == "builder-a":
            return {
                "assetPositions": [
                    {
                        "position": {
                            "coin": "HIP3",
                            "szi": "1.5",
                            "entryPx": "10",
                            "leverage": {"value": 5},
                            "unrealizedPnl": "2.0",
                            "returnOnEquity": "0.1",
                        }
                    }
                ]
            }
        return {"assetPositions": []}

    async def fake_get_market_prices(dex=""):
        if dex == "builder-a":
            return {"HIP3": 12.0}
        return {}

    monkeypatch.setattr(hyperliquid_api, "get_perp_dexs", fake_get_perp_dexs)
    monkeypatch.setattr(hyperliquid_api, "get_clearinghouse_state", fake_get_clearinghouse_state)
    monkeypatch.setattr(hyperliquid_api, "get_market_prices", fake_get_market_prices)

    report = asyncio.run(hyperliquid_api.get_positions_report("0xabc"))

    assert report["status"] == "ok"
    assert len(report["positions"]) == 1
    assert report["positions"][0]["display_coin"] == "builder-a:HIP3"
    assert report["positions"][0]["current_px"] == 12.0
