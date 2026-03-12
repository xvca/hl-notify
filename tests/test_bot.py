from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot import (
    TELEGRAM_USER_ID,
    cmd_fundingfilter,
    cmd_label,
    cmd_positions,
    cmd_watch,
    format_funding_config,
    format_funding_rule,
    format_wallet_name,
    parse_optional_threshold,
    resolve_wallet_ref,
    should_send_funding_notification,
)


def make_update():
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=TELEGRAM_USER_ID),
        message=message,
    )


def make_context(*args):
    return SimpleNamespace(args=list(args))


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


def test_resolve_wallet_ref_accepts_label(monkeypatch):
    monkeypatch.setattr("bot.storage.find_wallet_by_label", lambda ref: "0xabc" if ref == "main" else None)

    assert resolve_wallet_ref("main") == "0xabc"
    assert resolve_wallet_ref("0x1234567890123456789012345678901234567890") == "0x1234567890123456789012345678901234567890"


def test_format_wallet_name_prefers_label(monkeypatch):
    monkeypatch.setattr("bot.storage.get_label", lambda address: "Main Wallet")
    assert format_wallet_name("0x1234567890123456789012345678901234567890") == "Main Wallet (0x1234...7890)"


@pytest.mark.anyio
async def test_cmd_watch_accepts_optional_label(monkeypatch):
    update = make_update()
    context = make_context("0x1234567890123456789012345678901234567890", "Main", "Wallet")
    subscribe = AsyncMock()

    monkeypatch.setattr("bot.storage.add_wallet", lambda address, label=None: label == "Main Wallet")
    monkeypatch.setattr("bot.storage.get_label", lambda address: "Main Wallet")
    monkeypatch.setattr("bot.ws_manager", SimpleNamespace(subscribe=subscribe))

    await cmd_watch(update, context)

    subscribe.assert_awaited_once_with("0x1234567890123456789012345678901234567890")
    update.message.reply_text.assert_awaited_once_with(
        "Watching Main Wallet (0x1234...7890)"
    )


@pytest.mark.anyio
async def test_cmd_label_updates_wallet_by_label(monkeypatch):
    update = make_update()
    context = make_context("main", "Desk", "Wallet")

    monkeypatch.setattr("bot.resolve_wallet_ref", lambda ref: "0x1234567890123456789012345678901234567890")
    monkeypatch.setattr("bot.storage.set_label", lambda address, label: "Desk Wallet")

    await cmd_label(update, context)

    update.message.reply_text.assert_awaited_once_with(
        "Updated label for 0x1234...7890 to Desk Wallet"
    )


@pytest.mark.anyio
async def test_cmd_fundingfilter_shows_config_for_label(monkeypatch):
    update = make_update()
    context = make_context("main")

    monkeypatch.setattr("bot.resolve_wallet_ref", lambda ref: "0x1234567890123456789012345678901234567890")
    monkeypatch.setattr(
        "bot.storage.get_funding_filters",
        lambda address: {
            "annualized_threshold": None,
            "usdc_threshold": 5.0,
        },
    )
    monkeypatch.setattr("bot.storage.get_label", lambda address: "Main Wallet")

    await cmd_fundingfilter(update, context)

    sent = update.message.reply_text.await_args.args[0]
    assert "Funding alerts for Main Wallet (0x1234...7890)" in sent
    assert "Rule: notify only when payment is at least $5" in sent


@pytest.mark.anyio
async def test_cmd_positions_rejects_unknown_label(monkeypatch):
    update = make_update()
    context = make_context("missing")

    monkeypatch.setattr("bot.resolve_wallet_ref", lambda ref: None)

    await cmd_positions(update, context)

    update.message.reply_text.assert_awaited_once_with(
        "Wallet not found. /watch it first."
    )
