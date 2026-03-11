from bot import (
    format_funding_config,
    format_funding_rule,
    parse_optional_threshold,
    should_send_funding_notification,
)


def test_parse_optional_threshold_accepts_off():
    assert parse_optional_threshold("off") is None
    assert parse_optional_threshold("12.5") == 12.5


def test_should_send_funding_notification_uses_or_logic(monkeypatch):
    monkeypatch.setattr(
        "bot.storage.get_funding_filters",
        lambda wallet: {
            "annualized_threshold": 20.0,
            "usdc_threshold": 5.0,
        },
    )

    assert should_send_funding_notification(
        "0xabc",
        {"usdc": "6", "fundingRate": "0.000001"},
    )
    assert should_send_funding_notification(
        "0xabc",
        {"usdc": "1", "fundingRate": "0.00003"},
    )
    assert not should_send_funding_notification(
        "0xabc",
        {"usdc": "1", "fundingRate": "0.000001"},
    )


def test_format_funding_config_shows_off_threshold():
    text = format_funding_config(
        "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303",
        {
            "annualized_threshold": None,
            "usdc_threshold": 5.0,
        },
    )

    assert "Annualized threshold: off" in text
    assert "USD threshold: $5" in text
    assert "Rule: notify only when payment is at least $5" in text
    assert "Usage: /fundingfilter 0xdfc24b077bc1425ad1dea75bcb6f8158e10df303 <annualized_pct|off> <usd|off>" in text
    assert "Example: /fundingfilter 0xdfc24b077bc1425ad1dea75bcb6f8158e10df303 off 5" in text


def test_format_funding_rule_for_unfiltered_wallet():
    assert format_funding_rule(
        {
            "annualized_threshold": None,
            "usdc_threshold": None,
        }
    ) == "notify on every funding event"


def test_format_funding_rule_for_annualized_only():
    assert format_funding_rule(
        {
            "annualized_threshold": 20.0,
            "usdc_threshold": None,
        }
    ) == "notify only when annualized funding is at least 20%"


def test_format_funding_rule_for_both_thresholds():
    assert format_funding_rule(
        {
            "annualized_threshold": 20.0,
            "usdc_threshold": 5.0,
        }
    ) == "notify when annualized funding is at least 20% or payment is at least $5"


def test_should_send_funding_notification_with_both_thresholds_off_means_no_filter(monkeypatch):
    monkeypatch.setattr(
        "bot.storage.get_funding_filters",
        lambda wallet: {
            "annualized_threshold": None,
            "usdc_threshold": None,
        },
    )

    assert should_send_funding_notification(
        "0xabc",
        {"usdc": "0.01", "fundingRate": "0.0000001"},
    )
