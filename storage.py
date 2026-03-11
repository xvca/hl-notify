import json
import os
from pathlib import Path
from config import DATA_DIR

CONFIG_PATH = Path(DATA_DIR) / "config.json"

DEFAULT_EVENTS = {
    "fills": True,
    "liquidations": True,
    "funding": True,
    "transfers": True,
}

DEFAULT_FUNDING_FILTERS = {
    "annualized_threshold": None,
    "usdc_threshold": None,
}


def _normalize_wallet(wallet: dict) -> dict:
    wallet.setdefault("label", None)
    wallet["events"] = {**DEFAULT_EVENTS, **wallet.get("events", {})}

    funding_filters = wallet.get("funding_filters", {})
    normalized_filters = {**DEFAULT_FUNDING_FILTERS}
    normalized_filters.update({
        k: funding_filters.get(k)
        for k in DEFAULT_FUNDING_FILTERS
        if k in funding_filters
    })
    wallet["funding_filters"] = normalized_filters
    return wallet


def _load() -> dict:
    if not CONFIG_PATH.exists():
        return {"wallets": {}}
    with open(CONFIG_PATH) as f:
        return json.load(f)


def _save(data: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)


def get_wallets() -> dict:
    wallets = _load()["wallets"]
    return {
        address: _normalize_wallet(wallet)
        for address, wallet in wallets.items()
    }


def add_wallet(address: str) -> bool:
    address = address.lower()
    data = _load()
    if address in data["wallets"]:
        return False
    data["wallets"][address] = {
        "label": None,
        "events": {**DEFAULT_EVENTS},
        "funding_filters": {**DEFAULT_FUNDING_FILTERS},
    }
    _save(data)
    return True


def remove_wallet(address: str) -> bool:
    address = address.lower()
    data = _load()
    if address not in data["wallets"]:
        return False
    del data["wallets"][address]
    _save(data)
    return True


def get_events(address: str) -> dict | None:
    address = address.lower()
    wallets = get_wallets()
    if address not in wallets:
        return None
    return wallets[address]["events"]


def toggle_event(address: str, event_type: str) -> bool | None:
    address = address.lower()
    data = _load()
    wallet = data["wallets"].get(address)
    if not wallet or event_type not in wallet["events"]:
        return None
    wallet["events"][event_type] = not wallet["events"][event_type]
    _save(data)
    return wallet["events"][event_type]


def is_event_enabled(address: str, event_type: str) -> bool:
    events = get_events(address)
    if events is None:
        return False
    return events.get(event_type, False)


def get_funding_filters(address: str) -> dict | None:
    address = address.lower()
    wallets = get_wallets()
    if address not in wallets:
        return None
    return wallets[address]["funding_filters"]


def set_funding_filters(
    address: str,
    annualized_threshold: float | None,
    usdc_threshold: float | None,
) -> dict | None:
    address = address.lower()
    data = _load()
    wallet = data["wallets"].get(address)
    if not wallet:
        return None

    normalized = _normalize_wallet(wallet)
    normalized["funding_filters"] = {
        "annualized_threshold": annualized_threshold,
        "usdc_threshold": usdc_threshold,
    }
    data["wallets"][address] = normalized
    _save(data)
    return normalized["funding_filters"]
